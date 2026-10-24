"""Transactional manual route progress, distinct from live vision lifecycle."""

from uuid import uuid4

from fastapi import APIRouter, Query, Request, Response, Security

from .database import Database
from .errors import BackendError
from .models import ErrorResponse, Identifier
from .route_models import (
    CheckpointRef, GuidanceEvent, MemoryResponse, NavigationProgress,
    ObstacleObservation, RouteAction, RouteList, RouteResponse,
)
from .route_store import RouteCatalog, read_route
from .settings import Settings
from .store import epoch_ms
from .vision import session_cookie, session_header


def current_navigation(connection, session_id):
    return connection.execute(
        "SELECT n.* FROM navigation_heads h JOIN navigation_sessions n ON h.navigation_id=n.navigation_id WHERE h.session_id=?",
        (session_id,),
    ).fetchone()


def invalidate_guidance(connection, navigation_id):
    connection.execute("UPDATE guidance_events SET valid=0 WHERE navigation_id=? AND valid=1", (navigation_id,))


def insert_event(connection, navigation_id, action, prior, resulting, index, timestamp):
    connection.execute(
        "INSERT INTO route_events(event_id,navigation_id,action,prior_state,resulting_state,checkpoint_index,timestamp) VALUES(?,?,?,?,?,?,?)",
        (str(uuid4()), navigation_id, action, prior, resulting, index, timestamp),
    )


def progress(connection, navigation, now, *, devices=None) -> NavigationProgress:
    route = read_route(connection, navigation["route_id"])
    checkpoints = route.checkpoints
    count = navigation["confirmed_count"]
    current = checkpoints[navigation["current_index"]] if navigation["current_index"] < len(checkpoints) else None
    row = connection.execute(
        "SELECT event_id,navigation_id,session_id,instruction,direction,created_at,expires_at,state_revision,checkpoint_id,valid FROM guidance_events WHERE navigation_id=? ORDER BY seq DESC LIMIT 1",
        (navigation["navigation_id"],),
    ).fetchone()
    event = None
    if row:
        values = dict(row)
        values["valid"] = bool(values["valid"] and values["expires_at"] > now and route.checked
                               and (devices is None or devices.can_guide(connection, navigation["session_id"]))
                               and navigation["state"] == "guiding" and values["state_revision"] == navigation["revision"])
        event = GuidanceEvent(**values)
    messages = {
        "idle": "Navigation stopped; confirmed progress is saved.",
        "guiding": "Follow the checked instruction and explicitly confirm the checkpoint. Physical position is not known.",
        "paused": "Navigation paused; confirm your situation before resuming.",
        "blocked": "Navigation blocked; confirmation and normal guidance are disabled.",
        "completed": "All checkpoints were explicitly confirmed; route completed.",
    }
    ref = lambda cp: CheckpointRef(checkpoint_id=cp.checkpoint_id, ordinal=cp.ordinal, landmark=cp.landmark)
    return NavigationProgress(
        session_id=navigation["session_id"], navigation_id=navigation["navigation_id"], route_id=route.route_id,
        state=navigation["state"], state_revision=navigation["revision"],
        current_checkpoint=ref(current) if current else None,
        confirmed_checkpoint_count=count, total_checkpoints=len(checkpoints),
        confirmed_checkpoints=tuple(ref(cp) for cp in checkpoints[:count]),
        instruction=event.instruction if event and event.valid else None,
        haptic_direction=event.direction if event and event.valid else None,
        guidance_event_id=event.event_id if event else None, guidance_event=event,
        status_message=messages[navigation["state"]],
        created_at=navigation["created_at"], updated_at=navigation["updated_at"],
        **(devices.progress_fields(connection, navigation["session_id"]) if devices else {}),
    )


class NavigationController:
    def __init__(self, database: Database, settings: Settings, clock=epoch_ms):
        self.database = database
        self.settings = settings
        self.clock = clock
        self.devices = None

    def _guidance(self, connection, navigation):
        route = read_route(connection, navigation["route_id"])
        if not route.checked:
            raise BackendError(409, "route_unchecked", "Human verification is required before route guidance")
        checkpoint = route.checkpoints[navigation["current_index"]]
        now = self.clock()
        invalidate_guidance(connection, navigation["navigation_id"])
        connection.execute(
            "INSERT INTO guidance_events(event_id,navigation_id,session_id,instruction,direction,created_at,expires_at,state_revision,checkpoint_id,valid) VALUES(?,?,?,?,?,?,?,?,?,1)",
            (str(uuid4()), navigation["navigation_id"], navigation["session_id"], checkpoint.instruction,
             checkpoint.direction, now, now + self.settings.guidance_ttl_ms, navigation["revision"], checkpoint.checkpoint_id),
        )

    def _apply(self, connection, request: RouteAction):
        now = self.clock()
        navigation = current_navigation(connection, request.session_id)
        revision = navigation["revision"] if navigation else 0
        if request.expected_revision is not None and request.expected_revision != revision:
            raise BackendError(409, "revision_conflict", "Navigation revision has changed; read current progress")
        if request.action == "start":
            route = read_route(connection, request.route_id)
            if not route.checked:
                raise BackendError(409, "route_unchecked", "Human verification is required before route guidance")
            if navigation:
                if request.expected_revision is None:
                    raise BackendError(409, "revision_required", "Starting a later navigation requires the current revision")
                if request.navigation_id is not None and request.navigation_id != navigation["navigation_id"]:
                    raise BackendError(409, "navigation_conflict", "Navigation identity has changed")
                if navigation["state"] not in {"idle", "completed"}:
                    raise BackendError(409, "invalid_transition", "Stop the current navigation before starting another")
                invalidate_guidance(connection, navigation["navigation_id"])
            navigation_id = str(uuid4())
            connection.execute(
                "INSERT INTO navigation_sessions(navigation_id,session_id,route_id,state,current_index,confirmed_count,revision,created_at,updated_at) VALUES(?,?,?,'guiding',0,0,?,?,?)",
                (navigation_id, request.session_id, route.route_id, revision + 1, now, now),
            )
            connection.execute(
                "INSERT INTO navigation_heads(session_id,navigation_id,revision) VALUES(?,?,?) ON CONFLICT(session_id) DO UPDATE SET navigation_id=excluded.navigation_id,revision=excluded.revision",
                (request.session_id, navigation_id, revision + 1),
            )
            insert_event(connection, navigation_id, "start", "idle", "guiding", 0, now)
            self._guidance(connection, current_navigation(connection, request.session_id))
            return

        if navigation is None or navigation["navigation_id"] != request.navigation_id:
            raise BackendError(409, "navigation_conflict", "Action does not refer to the current navigation")
        if request.route_id is not None and request.route_id != navigation["route_id"]:
            raise BackendError(409, "route_conflict", "Route does not match the current navigation")
        state = navigation["state"]
        allowed = {
            "idle": set(), "guiding": {"confirm", "repeat", "pause", "stop"},
            "paused": {"resume", "stop"}, "blocked": {"stop"}, "completed": {"stop"},
        }
        if request.action not in allowed[state]:
            raise BackendError(409, "invalid_transition", "Action is invalid in the current navigation state")
        if request.action == "repeat":
            self._guidance(connection, navigation)
            return  # New cue, same state/revision/progress; no progress event.
        route = read_route(connection, navigation["route_id"])
        if request.action in {"confirm", "resume"} and not route.checked:
            raise BackendError(409, "route_unchecked", "Human verification is required before route guidance")
        index, count = navigation["current_index"], navigation["confirmed_count"]
        next_state = {"pause": "paused", "resume": "guiding", "stop": "idle"}.get(request.action, state)
        if request.action == "confirm":
            count += 1
            index += 1
            next_state = "completed" if count == len(route.checkpoints) else "guiding"
        invalidate_guidance(connection, navigation["navigation_id"])
        connection.execute(
            "UPDATE navigation_sessions SET state=?,current_index=?,confirmed_count=?,revision=?,updated_at=? WHERE navigation_id=?",
            (next_state, index, count, revision + 1, now, navigation["navigation_id"]),
        )
        connection.execute("UPDATE navigation_heads SET revision=? WHERE session_id=?", (revision + 1, request.session_id))
        insert_event(connection, navigation["navigation_id"], request.action, state, next_state, navigation["current_index"], now)
        if next_state == "guiding":
            self._guidance(connection, current_navigation(connection, request.session_id))

    def control(self, request: RouteAction) -> RouteResponse:
        serialized = request.model_dump_json()
        error = None
        with self.database.transaction(write=True) as connection:
            if self.devices and self.devices.enabled:
                self.devices.after_navigation(connection, request.session_id)
            previous = connection.execute("SELECT * FROM route_actions WHERE session_id=? AND action_id=?", (request.session_id, request.action_id)).fetchone()
            if previous:
                if previous["request_json"] != serialized:
                    raise BackendError(409, "action_id_conflict", "Action ID was already used for different contents")
                if previous["error_status"] is not None:
                    raise BackendError(previous["error_status"], previous["error_code"], previous["error_message"])
                applied_revision = previous["applied_revision"]
            else:
                head = current_navigation(connection, request.session_id)
                count = connection.execute("SELECT COUNT(*) FROM route_actions WHERE session_id=?", (request.session_id,)).fetchone()[0]
                if count >= self.settings.max_route_actions_per_session and not (request.action == "stop" and head and head["state"] != "idle" and count == self.settings.max_route_actions_per_session):
                    raise BackendError(429, "route_action_capacity", "Route action history is full")
                # A savepoint ensures a failed action cannot leave partial progress.
                connection.execute("SAVEPOINT navigation_action")
                try:
                    self._apply(connection, request)
                    if self.devices and self.devices.enabled:
                        self.devices.after_navigation(connection, request.session_id)
                except BackendError as exc:
                    connection.execute("ROLLBACK TO navigation_action")
                    error = exc
                finally:
                    connection.execute("RELEASE navigation_action")
                head = current_navigation(connection, request.session_id)
                applied_revision = head["revision"] if head else 0
                # A rejected stale stop cannot consume the reserved terminal
                # action slot and prevent a subsequent valid stop.
                if not (error and count >= self.settings.max_route_actions_per_session):
                    connection.execute(
                        "INSERT INTO route_actions(session_id,action_id,request_json,navigation_id,applied_revision,error_status,error_code,error_message) VALUES(?,?,?,?,?,?,?,?)",
                        (request.session_id, request.action_id, serialized, head["navigation_id"] if head else None, applied_revision,
                         error.status_code if error else None, error.code if error else None, error.message if error else None),
                    )
            if error is None:
                head = current_navigation(connection, request.session_id)
                result = RouteResponse(**progress(connection, head, self.clock(), devices=self.devices).model_dump(), action_id=request.action_id,
                                       duplicate=previous is not None, applied_revision=applied_revision)
        if error:
            raise error
        return result

    def recover_after_restart(self):
        """Require explicit resume; persisted progress never establishes position."""
        with self.database.transaction(write=True) as connection:
            connection.execute("UPDATE guidance_events SET valid=0 WHERE valid=1")
            rows = connection.execute("SELECT * FROM navigation_sessions WHERE state='guiding'").fetchall()
            for navigation in rows:
                revision = navigation["revision"] + 1
                connection.execute("UPDATE navigation_sessions SET state='paused',revision=?,updated_at=? WHERE navigation_id=?",
                                   (revision, self.clock(), navigation["navigation_id"]))
                connection.execute("UPDATE navigation_heads SET revision=? WHERE navigation_id=?", (revision, navigation["navigation_id"]))
                insert_event(connection, navigation["navigation_id"], "process_restart", "guiding", "paused", navigation["current_index"], self.clock())

    def apply_obstacle(self, session_id: str, navigation_id: str, expected_revision: int, observation: ObstacleObservation):
        """Internal sensor seam; caller must verify freshness/validity."""
        with self.database.transaction(write=True) as connection:
            result = self.apply_obstacle_in_transaction(connection, session_id, navigation_id, expected_revision, observation)
            if self.devices and self.devices.enabled:
                self.devices.after_navigation(connection, session_id)
                result = progress(connection, current_navigation(connection, session_id), self.clock(), devices=self.devices)
            return result

    def _sensor_transition(self, connection, navigation, next_state, action):
        if navigation['state'] != next_state:
            invalidate_guidance(connection, navigation['navigation_id'])
            connection.execute("UPDATE navigation_sessions SET state=?,revision=revision+1,updated_at=? WHERE navigation_id=?", (next_state, self.clock(), navigation['navigation_id']))
            connection.execute("UPDATE navigation_heads SET revision=revision+1 WHERE session_id=?", (navigation['session_id'],))
            insert_event(connection, navigation['navigation_id'], action, navigation['state'], next_state, navigation['current_index'], self.clock())
            if self.devices and self.devices.enabled:
                # Retain human confirmations/actions; bound only sensor-generated
                # audit transitions so a noisy device cannot grow history forever.
                connection.execute(
                    "DELETE FROM route_events WHERE navigation_id=? AND action IN ('sensor_unknown','sensor_caution','sensor_danger','sensor_clear','controller_reboot','obstacle_clear','obstacle_block') AND seq NOT IN (SELECT seq FROM route_events WHERE navigation_id=? AND action IN ('sensor_unknown','sensor_caution','sensor_danger','sensor_clear','controller_reboot','obstacle_clear','obstacle_block') ORDER BY seq DESC LIMIT ?)",
                    (navigation['navigation_id'], navigation['navigation_id'], self.settings.device_events_per_navigation),
                )

    def hold_for_device(self, connection, session_id, reason):
        """Conservative hold for unknown/caution/danger; never labels unknown clear."""
        navigation = current_navigation(connection, session_id)
        if navigation and navigation['state'] in {'guiding', 'paused'}:
            self._sensor_transition(connection, navigation, 'blocked', reason)

    def apply_obstacle_in_transaction(self, connection, session_id, navigation_id, expected_revision, observation):
        navigation = current_navigation(connection, session_id)
        if navigation is None or navigation['navigation_id'] != navigation_id or navigation['revision'] != expected_revision:
            raise BackendError(409, 'navigation_conflict', 'Navigation identity or revision has changed')
        if observation.fresh and observation.valid and observation.obstacle is not None:
            state = navigation['state']
            next_state = 'blocked' if observation.obstacle and state in {'guiding', 'paused'} else 'paused' if not observation.obstacle and state == 'blocked' else state
            self._sensor_transition(connection, navigation, next_state, 'obstacle_block' if next_state == 'blocked' else 'obstacle_clear')
        return progress(connection, current_navigation(connection, session_id), self.clock(), devices=self.devices)


def create_navigation_router(database, catalog, controller, memory, auth):
    router = APIRouter(dependencies=[Security(session_header), Security(session_cookie)],
                       responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503)})

    @router.get("/routes", response_model=RouteList)
    async def routes(request: Request, response: Response, session_id: Identifier, limit: int = Query(25, ge=1, le=100)):
        auth.authorize(request, session_id)
        response.headers["Cache-Control"] = "no-store"
        return await database.run(catalog.list, limit)

    @router.post("/route", response_model=RouteResponse)
    async def route(request: Request, response: Response, action: RouteAction):
        auth.authorize(request, action.session_id)
        response.headers["Cache-Control"] = "no-store"
        return await database.run(controller.control, action)

    @router.get("/memory", response_model=MemoryResponse)
    async def recall(request: Request, response: Response, session_id: Identifier,
                     include_events: bool = False, limit: int = Query(25, ge=1, le=100)):
        auth.authorize(request, session_id)
        response.headers["Cache-Control"] = "no-store"
        return await database.run(memory.read, session_id, include_events=include_events, limit=limit)

    return router
