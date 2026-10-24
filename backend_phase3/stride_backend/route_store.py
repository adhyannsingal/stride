"""Saved checked routes and explicitly unverified development fixtures."""

import argparse

from .database import Database
from .errors import BackendError
from .route_models import Checkpoint, RouteList, SavedRoute
from .settings import Settings
from .store import epoch_ms


def read_route(connection, route_id: str) -> SavedRoute:
    row = connection.execute("SELECT * FROM routes WHERE route_id=?", (route_id,)).fetchone()
    if row is None:
        raise BackendError(404, "route_not_found", "Saved route does not exist")
    checkpoints = connection.execute(
        "SELECT checkpoint_id,ordinal,instruction,direction,landmark,return_instruction,return_direction,return_checked FROM checkpoints WHERE route_id=? ORDER BY ordinal",
        (route_id,),
    ).fetchall()
    return SavedRoute(**dict(row), checkpoints=tuple(Checkpoint(**dict(cp)) for cp in checkpoints))


def list_routes(connection, limit: int) -> RouteList:
    rows = connection.execute("SELECT route_id FROM routes ORDER BY route_id LIMIT ?", (limit,)).fetchall()
    return RouteList(routes=tuple(read_route(connection, row["route_id"]) for row in rows))


class RouteCatalog:
    def __init__(self, database: Database, clock=epoch_ms):
        self.database = database
        self.clock = clock

    @staticmethod
    def _insert(connection, route: SavedRoute):
        connection.execute(
            "INSERT INTO routes(route_id,name,description,created_at,updated_at,checked,demo_fixture,verification_note) VALUES(?,?,?,?,?,?,?,?)",
            (route.route_id, route.name, route.description, route.created_at, route.updated_at,
             int(route.checked), int(route.demo_fixture), route.verification_note),
        )
        connection.executemany(
            "INSERT INTO checkpoints(checkpoint_id,route_id,ordinal,instruction,direction,landmark,return_instruction,return_direction,return_checked) VALUES(?,?,?,?,?,?,?,?,?)",
            [(cp.checkpoint_id, route.route_id, cp.ordinal, cp.instruction, cp.direction,
              cp.landmark, cp.return_instruction, cp.return_direction, int(cp.return_checked)) for cp in route.checkpoints],
        )

    def add_route(self, route: SavedRoute):
        route = SavedRoute.model_validate(route.model_dump())
        with self.database.transaction(write=True) as connection:
            if connection.execute("SELECT 1 FROM routes WHERE route_id=?", (route.route_id,)).fetchone():
                raise BackendError(409, "route_exists", "Saved route already exists")
            self._insert(connection, route)

    def install_fixtures(self):
        now = self.clock()
        definitions = (
            ("demo-hallway", "Demo hallway A → B → C", (
                ("A", "Proceed to checkpoint A.", "straight"),
                ("B", "Turn left at checkpoint B.", "left"),
                ("C", "Stop at checkpoint C.", "stop"),
            )),
            ("demo-tabletop", "Demo tabletop markers", (
                ("A", "Proceed to tabletop marker A in the supervised test layout.", "straight"),
                ("B", "Stop at tabletop marker B.", "stop"),
            )),
        )
        with self.database.transaction(write=True) as connection:
            for route_id, name, checkpoints in definitions:
                if connection.execute("SELECT 1 FROM routes WHERE route_id=?", (route_id,)).fetchone():
                    continue  # Never replace instructions or a human verification.
                route = SavedRoute(
                    route_id=route_id, name=name, created_at=now, updated_at=now,
                    description="DEMO FIXTURE: not tied to a real building; requires human verification of the actual supervised layout before guidance.",
                    checkpoints=tuple(Checkpoint(
                        checkpoint_id=f"{route_id}:{label}", ordinal=index,
                        instruction=instruction, direction=direction, landmark=f"Demo marker {label}",
                    ) for index, (label, instruction, direction) in enumerate(checkpoints)),
                )
                self._insert(connection, route)

    def mark_checked(self, route_id: str, verification_note: str) -> SavedRoute:
        note = verification_note.strip()
        if not 3 <= len(note) <= 1000:
            raise BackendError(422, "verification_note_required", "Record a human verification note of 3 to 1000 characters")
        with self.database.transaction(write=True) as connection:
            read_route(connection, route_id)
            connection.execute(
                "UPDATE routes SET checked=1,verification_note=?,updated_at=? WHERE route_id=?",
                (note, self.clock(), route_id),
            )
            return read_route(connection, route_id)

    def list(self, limit=25) -> RouteList:
        with self.database.transaction() as connection:
            return list_routes(connection, limit)


def main():
    parser = argparse.ArgumentParser(description="Mark instructions checked only after human verification of the actual demo layout")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("route_id")
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    settings = Settings()
    database = Database(settings.database_path)
    database.initialize()
    catalog = RouteCatalog(database)
    if settings.load_demo_routes:
        catalog.install_fixtures()
    result = catalog.mark_checked(args.route_id, args.note)
    print(f"Marked {result.route_id} checked; demo_fixture={result.demo_fixture}")


if __name__ == "__main__":
    main()
