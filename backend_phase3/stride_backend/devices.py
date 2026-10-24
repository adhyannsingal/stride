"""Transactional controller monitoring and bounded optional remote haptic cues."""

import hashlib
import json
from uuid import uuid4

from .device_models import AckResponse, CommandPoll, DeviceStatus, HapticCommand, PairResponse, TelemetryResponse
from .errors import BackendError
from .navigation import current_navigation
from .obstacles import classify
from .route_models import ObstacleObservation
from .store import epoch_ms, monotonic_ms

ACTIVE = ('issued', 'delivered', 'received')


class DeviceService:
    def __init__(self, database, settings, navigation, clock=monotonic_ms, epoch_clock=epoch_ms):
        self.database, self.settings, self.navigation = database, settings, navigation
        self.clock, self.epoch = clock, epoch_clock
        self.runtime_id = str(uuid4())
        self.enabled = bool(settings.controller_sessions)

    def initialize(self):
        self.runtime_id = str(uuid4())
        with self.database.transaction(write=True) as connection:
            # A process restart cannot renew observations or remote actuation.
            connection.execute("UPDATE haptic_commands SET status='canceled' WHERE status IN ('issued','delivered','received')")
            connection.execute("UPDATE device_state SET runtime_id=NULL,contact_runtime=NULL,clear_count=0,obstacle_state='unknown'")
            existing = {row[0] for row in connection.execute("SELECT device_id FROM devices")}
            new = set(self.settings.controller_sessions) - existing
            if len(existing) + len(new) > self.settings.max_controllers:
                raise BackendError(429, "controller_capacity", "Registered controller capacity reached")
            for row in connection.execute("SELECT device_id,session_id FROM devices").fetchall():
                if row['session_id'] is not None and self.settings.controller_sessions.get(row['device_id']) != row['session_id']:
                    connection.execute("UPDATE devices SET session_id=NULL,paired_at=NULL,last_event_key=NULL WHERE device_id=?", (row['device_id'],))
            for device_id, allowed_session in self.settings.controller_sessions.items():
                connection.execute("INSERT OR IGNORE INTO devices(device_id,registered_at) VALUES(?,?)", (device_id, self.epoch()))
                connection.execute("INSERT OR IGNORE INTO device_state(device_id) VALUES(?)", (device_id,))
                row = connection.execute("SELECT session_id FROM devices WHERE device_id=?", (device_id,)).fetchone()
                if row['session_id'] is not None and row['session_id'] != allowed_session:
                    connection.execute("UPDATE devices SET session_id=NULL,paired_at=NULL,last_event_key=NULL WHERE device_id=?", (device_id,))

    def _device(self, connection, device_id, *, paired=False):
        if device_id not in self.settings.controller_sessions:
            raise BackendError(403, "device_access_denied", "Controller is not provisioned")
        row = connection.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        if row is None:
            raise BackendError(404, "device_not_registered", "Controller is not registered")
        if paired and row['session_id'] != self.settings.controller_sessions[device_id]:
            raise BackendError(409, "device_not_paired", "An authorized UI session must pair this controller first")
        return row

    def _for_session(self, connection, session_id):
        row = connection.execute("SELECT * FROM devices WHERE session_id=?", (session_id,)).fetchone()
        return row if row and self.settings.controller_sessions.get(row['device_id']) == session_id else None

    def _observation(self, connection, device_id):
        row = connection.execute("SELECT * FROM device_state WHERE device_id=?", (device_id,)).fetchone()
        fresh = bool(row and row['runtime_id'] == self.runtime_id and row['received_mono'] is not None
                     and 0 <= self.clock() - row['received_mono'] <= self.settings.telemetry_fresh_ms)
        obstacle = row['obstacle_state'] if fresh and row['sensor_valid'] else 'unknown'
        return row, fresh, obstacle

    def progress_fields(self, connection, session_id):
        device = self._for_session(connection, session_id)
        if not device:
            return {'sensor_monitoring': 'not_associated', 'paired_device_id': None, 'obstacle_state': None}
        state, fresh, obstacle = self._observation(connection, device['device_id'])
        return {'sensor_monitoring': 'fresh_measurement' if fresh and state['sensor_valid'] else 'unknown',
                'paired_device_id': device['device_id'], 'obstacle_state': obstacle}

    def pair(self, device_id, session_id):
        if self.settings.controller_sessions.get(device_id) != session_id:
            raise BackendError(403, "pairing_denied", "Controller is not provisioned for this UI session")
        with self.database.transaction(write=True) as connection:
            row = self._device(connection, device_id)
            duplicate = row['session_id'] == session_id
            if not duplicate:
                connection.execute("UPDATE devices SET session_id=?,paired_at=?,last_event_key=NULL WHERE device_id=?", (session_id, self.epoch(), device_id))
            self.after_navigation(connection, session_id)
            return PairResponse(device_id=device_id, session_id=session_id, duplicate=duplicate)

    def _contact(self, connection, device_id, receipt_ms=None, receipt_mono=None):
        connection.execute("UPDATE device_state SET contact_ms=?,contact_mono=?,contact_runtime=? WHERE device_id=?",
                           (self.epoch() if receipt_ms is None else receipt_ms,
                            self.clock() if receipt_mono is None else receipt_mono, self.runtime_id, device_id))

    def ingest(self, telemetry, receipt_ms, receipt_mono):
        data = telemetry
        canonical = json.dumps(data.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self.database.transaction(write=True) as connection:
            device = self._device(connection, data.device_id, paired=True)
            old, old_fresh, previous = self._observation(connection, data.device_id)
            duplicate = False
            same_boot = old['boot_id'] == data.boot_id
            if same_boot:
                if data.sequence < old['sequence']:
                    raise BackendError(409, "telemetry_sequence_regression", "Sequence must increase within a controller boot")
                if data.sequence == old['sequence']:
                    if digest != old['payload_hash']:
                        raise BackendError(409, "telemetry_conflict", "Sequence was already used for different telemetry")
                    duplicate = True  # No receipt/heartbeat/measurement renewal.
                elif data.uptime_ms < old['uptime_ms']:
                    raise BackendError(409, "uptime_regression", "Uptime cannot decrease within a boot")
            else:
                known = connection.execute("SELECT 1 FROM device_boots WHERE device_id=? AND boot_id=?", (data.device_id, data.boot_id)).fetchone()
                if known:
                    raise BackendError(409, "retired_boot", "Packets from a previous boot cannot become current")
                count = connection.execute("SELECT COUNT(*) FROM device_boots WHERE device_id=?", (data.device_id,)).fetchone()[0]
                if count >= self.settings.max_boots_per_device:
                    raise BackendError(429, "boot_history_capacity", "Controller boot history is full; operator reprovisioning is required")
            if not duplicate:
                if not self.settings.local_dev and data.source != 'real':
                    raise BackendError(422, "non_live_telemetry", "Production controllers must declare real telemetry provenance")
                if not same_boot:
                    connection.execute("UPDATE device_boots SET retired=1 WHERE device_id=?", (data.device_id,))
                    connection.execute("INSERT INTO device_boots(device_id,boot_id,retired,first_received_ms) VALUES(?,?,0,?)", (data.device_id, data.boot_id, receipt_ms))
                    connection.execute("UPDATE haptic_commands SET status='canceled' WHERE device_id=? AND status IN ('issued','delivered','received')", (data.device_id,))
                    connection.execute("UPDATE devices SET last_event_key=NULL WHERE device_id=?", (data.device_id,))
                    # Reboot is a generation boundary even if its first reading is clear.
                    self.navigation.hold_for_device(connection, device['session_id'], 'controller_reboot')
                obstacle, valid, reason = classify(data.distance_cm, data.measurement_valid, data.sensor_status,
                                                  previous if same_boot and old_fresh else 'unknown', self.settings)
                recovering = valid and data.distance_cm > self.settings.obstacle_caution_cm + self.settings.obstacle_hysteresis_cm
                clear_count = min(self.settings.obstacle_recovery_samples,
                                  (old['clear_count'] if same_boot and old_fresh else 0) + 1) if recovering else 0
                connection.execute(
                    "UPDATE device_state SET boot_id=?,sequence=?,uptime_ms=?,payload_hash=?,received_ms=?,received_mono=?,runtime_id=?,distance_cm=?,sensor_valid=?,measurement_reason=?,obstacle_state=?,clear_count=?,battery_percent=?,firmware_version=?,source=? WHERE device_id=?",
                    (data.boot_id, data.sequence, data.uptime_ms, digest, receipt_ms, receipt_mono, self.runtime_id,
                     data.distance_cm, int(valid), reason, obstacle, clear_count, data.battery_percent, data.firmware_version, data.source, data.device_id),
                )
                if valid:
                    connection.execute("UPDATE device_state SET last_valid_distance_cm=?,last_valid_ms=?,last_valid_mono=?,last_valid_runtime=? WHERE device_id=?",
                                       (data.distance_cm, receipt_ms, receipt_mono, self.runtime_id, data.device_id))
                self._contact(connection, data.device_id, receipt_ms, receipt_mono)
                connection.execute(
                    "INSERT INTO device_telemetry(device_id,boot_id,sequence,uptime_ms,received_ms,distance_cm,measurement_valid,sensor_valid,measurement_reason,source,battery_percent,sensor_status,firmware_version,diagnostics_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (data.device_id, data.boot_id, data.sequence, data.uptime_ms, receipt_ms, data.distance_cm,
                     int(data.measurement_valid), int(valid), reason, data.source, data.battery_percent, data.sensor_status,
                     data.firmware_version, json.dumps(data.diagnostics, allow_nan=False)),
                )
                connection.execute("DELETE FROM device_telemetry WHERE device_id=? AND row_id NOT IN (SELECT row_id FROM device_telemetry WHERE device_id=? ORDER BY row_id DESC LIMIT ?)",
                                   (data.device_id, data.device_id, self.settings.telemetry_history_per_device))
            self.after_navigation(connection, device['session_id'])
            state = self._status(connection, data.device_id)
            return TelemetryResponse(device_id=data.device_id, duplicate=duplicate,
                                     received_ms=state.last_telemetry_received_ms, obstacle_state=state.obstacle_state,
                                     telemetry_fresh=state.telemetry_fresh, sensor_valid=state.sensor_valid,
                                     measurement_reason=state.measurement_reason,
                                     navigation_state=state.navigation_state, navigation_revision=state.navigation_revision)

    def synchronize(self, connection, session_id):
        device = self._for_session(connection, session_id)
        if not device:
            return
        state, fresh, obstacle = self._observation(connection, device['device_id'])
        navigation = current_navigation(connection, session_id)
        if not navigation:
            return
        recovered = fresh and obstacle == 'clear' and state['clear_count'] >= self.settings.obstacle_recovery_samples
        if not recovered:
            self.navigation.hold_for_device(connection, session_id, 'sensor_' + obstacle)
        elif navigation['state'] == 'blocked':
            self.navigation.apply_obstacle_in_transaction(
                connection, session_id, navigation['navigation_id'], navigation['revision'],
                ObstacleObservation(fresh=True, valid=True, obstacle=False),
            )

    def can_guide(self, connection, session_id):
        device = self._for_session(connection, session_id)
        if not device:
            return True  # Explicit Phase 3 no-device/demo mode.
        state, fresh, obstacle = self._observation(connection, device['device_id'])
        return fresh and obstacle == 'clear' and state['clear_count'] >= self.settings.obstacle_recovery_samples

    def after_navigation(self, connection, session_id):
        self.synchronize(connection, session_id)
        self._expire(connection)
        device = self._for_session(connection, session_id)
        navigation = current_navigation(connection, session_id)
        if not device or not navigation:
            return
        state, fresh, obstacle = self._observation(connection, device['device_id'])
        if not state['boot_id']:
            return
        guidance = connection.execute("SELECT * FROM guidance_events WHERE navigation_id=? ORDER BY seq DESC LIMIT 1", (navigation['navigation_id'],)).fetchone()
        if navigation['state'] == 'guiding' and fresh and obstacle == 'clear' and state['clear_count'] >= self.settings.obstacle_recovery_samples and guidance and guidance['valid'] and guidance['expires_at'] > self.epoch():
            kind, priority = guidance['direction'], 80 if guidance['direction'] == 'stop' else 10
            key, guidance_id = 'guide:' + guidance['event_id'], guidance['event_id']
            expiry = min(guidance['expires_at'], self.epoch() + self.settings.haptic_ttl_ms)
        else:
            danger_latched = obstacle == 'danger' or (device['last_event_key'] or '').startswith('stop:')
            kind = 'stop' if navigation['state'] == 'blocked' and danger_latched else 'cancel'
            priority = 100 if kind == 'stop' else 90
            key = f"{kind}:{navigation['navigation_id']}:{navigation['revision']}"
            guidance_id = None
            expiry = self.epoch() + self.settings.haptic_ttl_ms
        if device['last_event_key'] == key:
            return
        connection.execute("UPDATE haptic_commands SET status='canceled' WHERE device_id=? AND status IN ('issued','delivered','received')", (device['device_id'],))
        command_id = str(uuid4())
        connection.execute(
            "INSERT INTO haptic_commands(command_id,device_id,session_id,boot_id,navigation_id,state_revision,event_key,guidance_event_id,kind,priority,created_at,expires_at,expires_mono,runtime_id,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'issued')",
            (command_id, device['device_id'], session_id, state['boot_id'], navigation['navigation_id'], navigation['revision'],
             key, guidance_id, kind, priority, self.epoch(), expiry, self.clock() + max(0, expiry - self.epoch()), self.runtime_id),
        )
        connection.execute("UPDATE devices SET last_event_key=?,last_command_id=? WHERE device_id=?", (key, command_id, device['device_id']))
        connection.execute("DELETE FROM haptic_commands WHERE device_id=? AND command_id NOT IN (SELECT command_id FROM haptic_commands WHERE device_id=? ORDER BY rowid DESC LIMIT ?)",
                           (device['device_id'], device['device_id'], self.settings.max_commands_per_device))

    def _expire(self, connection):
        connection.execute("UPDATE haptic_commands SET status='expired' WHERE status IN ('issued','delivered','received') AND (runtime_id!=? OR expires_mono<=? OR expires_at<=?)", (self.runtime_id, self.clock(), self.epoch()))

    def _related(self, connection, command, device):
        navigation = current_navigation(connection, device['session_id'])
        state, _, _ = self._observation(connection, device['device_id'])
        return bool(command['runtime_id'] == self.runtime_id and state['boot_id'] == command['boot_id'] and navigation
                    and navigation['navigation_id'] == command['navigation_id'] and navigation['revision'] == command['state_revision'])

    def _command(self, row):
        remaining = max(0, min(row['expires_at'] - self.epoch(), row['expires_mono'] - self.clock())) if row['runtime_id'] == self.runtime_id else 0
        return HapticCommand(**{key: row[key] for key in (
            'command_id', 'device_id', 'session_id', 'boot_id', 'navigation_id', 'state_revision', 'kind', 'priority', 'created_at', 'expires_at', 'status')},
            remaining_ttl_ms=remaining, execution_reported=row['status'] == 'executed')

    def poll(self, device_id):
        with self.database.transaction(write=True) as connection:
            device = self._device(connection, device_id, paired=True)
            self._contact(connection, device_id)
            self.after_navigation(connection, device['session_id'])
            rows = connection.execute("SELECT * FROM haptic_commands WHERE device_id=? AND status='issued' ORDER BY priority DESC,rowid DESC", (device_id,)).fetchall()
            for row in rows:
                if not self._related(connection, row, device):
                    connection.execute("UPDATE haptic_commands SET status='canceled' WHERE command_id=?", (row['command_id'],))
                    continue
                connection.execute("UPDATE haptic_commands SET status='delivered',delivered_at=? WHERE command_id=?", (self.epoch(), row['command_id']))
                updated = connection.execute("SELECT * FROM haptic_commands WHERE command_id=?", (row['command_id'],)).fetchone()
                return CommandPoll(device_id=device_id, server_ms=self.epoch(), command=self._command(updated))
            return CommandPoll(device_id=device_id, server_ms=self.epoch())

    def acknowledge(self, acknowledgment):
        error = None
        with self.database.transaction(write=True) as connection:
            try:
                result = self._acknowledge(connection, acknowledgment)
            except BackendError as exc:
                error = exc
        if error:
            raise error
        return result

    def _acknowledge(self, connection, data):
        device = self._device(connection, data.device_id, paired=True)
        self.after_navigation(connection, device['session_id'])
        row = connection.execute("SELECT * FROM haptic_commands WHERE command_id=?", (data.command_id,)).fetchone()
        if row is None:
            raise BackendError(404, 'command_not_found', 'Command is unknown or outside retained history')
        if row['device_id'] != data.device_id:
            raise BackendError(403, 'command_access_denied', 'Command belongs to another controller')
        if not self._related(connection, row, device):
            raise BackendError(409, 'obsolete_command', 'Command belongs to an obsolete boot or navigation revision')
        prior_ack = connection.execute("SELECT 1 FROM haptic_acknowledgments WHERE command_id=? AND status=?", (data.command_id, data.status)).fetchone()
        if not prior_ack:
            allowed = {'delivered': {'received', 'rejected', 'expired'}, 'received': {'executed', 'rejected', 'expired'}}
            permitted = data.status in allowed.get(row['status'], set()) or (row['status'] == 'expired' and data.status == 'expired' and row['delivered_at'] is not None)
            if not permitted:
                raise BackendError(409, 'invalid_ack_transition', 'Acknowledgment is invalid for the current command state')
            connection.execute("INSERT INTO haptic_acknowledgments(command_id,status,received_at) VALUES(?,?,?)", (data.command_id, data.status, self.epoch()))
            connection.execute("UPDATE haptic_commands SET status=? WHERE command_id=?", (data.status, data.command_id))
        self._contact(connection, data.device_id)
        updated = connection.execute("SELECT * FROM haptic_commands WHERE command_id=?", (data.command_id,)).fetchone()
        return AckResponse(device_id=data.device_id, command_id=data.command_id, duplicate=prior_ack is not None,
                           status=updated['status'], execution_reported=updated['status'] == 'executed')


    def _status(self, connection, device_id):
        device = self._device(connection, device_id)
        state, fresh, obstacle = self._observation(connection, device_id)
        contact_fresh = bool(state['contact_runtime'] == self.runtime_id and state['contact_mono'] is not None
                             and 0 <= self.clock() - state['contact_mono'] <= self.settings.controller_heartbeat_ms)
        availability = 'connected' if contact_fresh else 'stale' if state['contact_ms'] is not None else 'unknown'
        age = None if state['received_ms'] is None else max(0, self.clock() - state['received_mono']) if state['runtime_id'] == self.runtime_id else max(0, self.epoch() - state['received_ms'])
        valid_age = None if state['last_valid_ms'] is None else max(0, self.clock() - state['last_valid_mono']) if state['last_valid_runtime'] == self.runtime_id else max(0, self.epoch() - state['last_valid_ms'])
        navigation = current_navigation(connection, device['session_id']) if device['session_id'] else None
        command = connection.execute("SELECT * FROM haptic_commands WHERE device_id=? ORDER BY rowid DESC LIMIT 1", (device_id,)).fetchone()
        acknowledgment = connection.execute("SELECT a.command_id FROM haptic_acknowledgments a JOIN haptic_commands c ON a.command_id=c.command_id WHERE c.device_id=? ORDER BY a.received_at DESC,a.rowid DESC LIMIT 1", (device_id,)).fetchone()
        pending = connection.execute("SELECT COUNT(*) FROM haptic_commands WHERE device_id=? AND status IN ('issued','delivered','received')", (device_id,)).fetchone()[0]
        reason = state['measurement_reason'] if fresh else 'no_telemetry' if state['received_ms'] is None else 'telemetry_stale'
        return DeviceStatus(
            device_id=device_id, session_id=device['session_id'], paired=device['session_id'] is not None,
            availability=availability, last_authenticated_contact_ms=state['contact_ms'], last_telemetry_received_ms=state['received_ms'],
            telemetry_age_ms=age, telemetry_fresh=fresh, measurement_fresh=bool(fresh and state['sensor_valid']),
            sensor_valid=bool(fresh and state['sensor_valid']), measurement_reason=reason,
            current_distance_cm=state['distance_cm'] if fresh and state['sensor_valid'] else None,
            last_reported_distance_cm=state['distance_cm'], last_valid_distance_cm=state['last_valid_distance_cm'],
            last_valid_distance_age_ms=valid_age, obstacle_state=obstacle, source=state['source'],
            boot_id=state['boot_id'], sequence=state['sequence'], uptime_ms=state['uptime_ms'], battery_percent=state['battery_percent'],
            firmware_version=state['firmware_version'], recovery_clear_count=state['clear_count'] if fresh else 0,
            recovery_required=self.settings.obstacle_recovery_samples,
            expected_telemetry_hz=self.settings.controller_expected_hz,
            measurement_timeout_ms=self.settings.telemetry_fresh_ms,
            heartbeat_timeout_ms=self.settings.controller_heartbeat_ms,
            navigation_state=navigation['state'] if navigation else None,
            navigation_revision=navigation['revision'] if navigation else None, pending_commands=pending,
            latest_command=self._command(command) if command else None,
            last_acknowledged_command_id=acknowledgment['command_id'] if acknowledgment else None,
        )

    def status(self, device_id):
        with self.database.transaction(write=True) as connection:
            device = self._device(connection, device_id)
            if device['session_id']:
                self.after_navigation(connection, device['session_id'])
            self._expire(connection)
            return self._status(connection, device_id)

    def maintenance(self):
        with self.database.transaction(write=True) as connection:
            for session_id in self.settings.controller_sessions.values():
                self.after_navigation(connection, session_id)
            self._expire(connection)
