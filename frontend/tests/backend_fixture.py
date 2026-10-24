"""Isolated frontend acceptance fixture using the UNMODIFIED backend on main.
No detector, physical device, deployment or real checked walking route is claimed.
Run with PYTHONPATH pointing at the backend checkout and uvicorn this module.
"""
from contextlib import asynccontextmanager
from tempfile import TemporaryDirectory
from pathlib import Path
from stride_backend.main import create_app
from stride_backend.settings import Settings

_tmp = TemporaryDirectory(prefix='stride-frontend-test-')
app = create_app(Settings(_env_file=None, local_dev=True,
    database_path=Path(_tmp.name) / 'test.sqlite3',
    session_tokens={'test-session':'test-only-token', 'second-session':'second-test-token', **{f'recovery-{i}':f'recovery-token-{i}' for i in range(5)}},
    controller_sessions={'test-controller':'test-session'},
    frontend_origins=('http://127.0.0.1:8443',)))
_original = app.router.lifespan_context
@asynccontextmanager
async def lifespan(app):
    async with _original(app):
        # TEST FIXTURE ONLY; never mark a real route checked from the UI.
        app.state.route_catalog.mark_checked('demo-hallway', 'TEST ONLY: synthetic route, not a physical verification')
        yield
app.router.lifespan_context = lifespan
