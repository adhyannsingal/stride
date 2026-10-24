"""Read-only capability probe of the existing Phase 2 app; no route simulation."""
import argparse
import json
from pathlib import Path
from fastapi.testclient import TestClient
from stride_backend.main import create_app
from stride_backend.settings import Settings


def inspect():
    app=create_app(Settings(_env_file=None,local_dev=True))
    published={(method,route.path) for route in app.routes for method in (getattr(route,'methods',None) or [])}
    required=[('GET','/routes'),('POST','/routes'),('POST','/route'),('GET','/memory'),('GET','/memory/export')]
    capabilities={f'{method} {path}':('PRESENT (needs behavioral testing)' if (method,path) in published else 'NOT IMPLEMENTED')
                  for method,path in required}
    with TestClient(app) as client:
        health=client.get('/health').status_code
    return {'scope':'existing Phase 2 backend route/memory inventory; no fake route responses',
            'health_http':health,'capabilities':capabilities,
            'saved_routes_ready':False,'airpods_playback_tested':False,
            'note':'Endpoint presence alone cannot prove persistence, checked directions, idempotency or physical audio.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='qa/navigation-readiness.json'); args=p.parse_args()
    result=inspect(); Path(args.output).write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
