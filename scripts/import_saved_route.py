"""Import a human-written named route into Phase 3 SQLite, always UNCHECKED."""
import argparse
import json
from pathlib import Path
from stride_backend.database import Database
from stride_backend.route_models import SavedRoute
from stride_backend.route_store import RouteCatalog
from stride_backend.settings import Settings
from stride_backend.store import epoch_ms


def import_route(definition,database):
    payload=dict(definition,checked=False,verification_note=None,created_at=epoch_ms(),updated_at=epoch_ms())
    payload['checkpoints']=[dict(step,return_checked=False) for step in definition['checkpoints']]
    route=SavedRoute.model_validate(payload)
    database.initialize(); RouteCatalog(database).add_route(route)
    return route


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('file'); args=p.parse_args()
    raw=Path(args.file).read_bytes()
    if len(raw)>262144: p.error('Route definition exceeds 256 KiB')
    route=import_route(json.loads(raw),Database(Settings().database_path))
    print(json.dumps({'route_id':route.route_id,'name':route.name,'checked':route.checked,
                      'note':'Saved only. Human verification of actual layout is required before guidance.'},indent=2))
