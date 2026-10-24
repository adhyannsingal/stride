import sqlite3

import pytest

from stride_backend.database import Database
from stride_backend.route_models import Checkpoint, SavedRoute
from stride_backend.route_store import RouteCatalog


def test_schema_initialization_is_versioned_and_idempotent(tmp_path):
    database = Database(tmp_path / "nested" / "test.sqlite3")
    database.initialize()
    database.initialize()
    with database.transaction() as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"routes", "checkpoints", "navigation_sessions", "route_events", "object_sightings", "route_actions", "guidance_events"} <= names
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_every_connection_enforces_foreign_keys(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    for _ in range(2):
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction(write=True) as connection:
                connection.execute("INSERT INTO checkpoints(checkpoint_id,route_id,ordinal,instruction,direction) VALUES(?,?,?,?,?)", ("orphan", "absent", 0, "test", "stop"))


def test_fixture_installation_preserves_manual_verification(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    catalog = RouteCatalog(database, lambda: 1000)
    catalog.install_fixtures()
    routes = catalog.list().routes
    assert len(routes) == 2
    assert all(route.demo_fixture and not route.checked for route in routes)
    assert len(next(route for route in routes if route.route_id == "demo-hallway").checkpoints) == 3
    catalog.mark_checked("demo-hallway", "TEST ONLY: human-check simulation")
    catalog.install_fixtures()
    assert next(route for route in catalog.list().routes if route.route_id == "demo-hallway").checked
    assert len(catalog.list().routes) == 2


def test_future_schema_version_is_not_destroyed(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    with database.transaction(write=True) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="Unsupported"):
        database.initialize()
    with database.transaction() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


def test_no_implicit_reverse_route():
    from pydantic import ValidationError
    checkpoint = Checkpoint(checkpoint_id="a", ordinal=0, instruction="Forward only", direction="left")
    assert checkpoint.return_instruction is None and checkpoint.return_checked is False
    with pytest.raises(ValidationError):
        checkpoint.model_validate({**checkpoint.model_dump(), "return_checked": True})
    with pytest.raises(ValidationError):
        SavedRoute(route_id="x", name="Invalid", created_at=0, updated_at=0, checkpoints=(checkpoint.model_copy(update={"ordinal": 2}),))
