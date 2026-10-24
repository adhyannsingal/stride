"""Run existing Phase 2 app + real detector on loopback, then actual webcam HTTP.
No new app/auth implementation; ephemeral credentials stay in memory and are not logged.
"""
import argparse
import asyncio
from pathlib import Path
import secrets
import socket
import threading
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4
import uvicorn
from stride_backend.main import create_app
from stride_backend.settings import Settings
from stride_backend.store import VerifiedClockAlignment, monotonic_ms
from scripts.live_smoke import run


def measure(args):
    with tempfile.TemporaryDirectory(prefix='stride-http-diagnostic-') as private_db:
        return _measure(args,Path(private_db)/'diagnostic.sqlite3')


def _measure(args,database_path):
    session,device=str(uuid4()),'phase2-local-webcam'
    secret=secrets.token_urlsafe(32)
    database_options={'database_path':database_path} if 'database_path' in Settings.model_fields else {}
    settings=Settings(_env_file=None,local_dev=False,device_token=secrets.token_urlsafe(32),
                      session_tokens={session:secret},detector_factory='app.vision.phase2:build_detector',**database_options)
    app=create_app(settings)
    if app.state.inference_worker.detector is None:
        raise RuntimeError('Real YOLO adapter failed to load; no substitute')
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(128)
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline: raise RuntimeError('Loopback server did not start')
            time.sleep(.01)
        def alignment(boot):
            # Capture and server run in this one process on the same OS clock.
            # This trusted registration is NOT a public endpoint/client assertion.
            app.state.frame_store.register_clock_alignment(session,VerifiedClockAlignment(
                device_id=device,boot_id=boot,offset_ms=0,uncertainty_ms=1,
                valid_until_monotonic_ms=monotonic_ms()+60000))
        options=SimpleNamespace(base_url=f'http://127.0.0.1:{port}',session_id=session,
                    device_id=device,camera=args.camera,seconds=args.seconds,protocol='phase2',output=args.output)
        report=asyncio.run(run(options,credentials={'X-Session-Token':secret},trusted_local_alignment=alignment))
        return report
    finally:
        server.should_exit=True
        thread.join(5)
        sock.close()
        if thread.is_alive(): raise RuntimeError('Loopback server did not shut down')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,default=60); p.add_argument('--camera',type=int,default=0)
    p.add_argument('--output',default='qa/phase2-webcam-http.json')
    args=p.parse_args()
    if args.seconds<=0: p.error('seconds must be positive')
    result=measure(args)
    raise SystemExit(0 if result['performance_gate']=='PASS' else 1)
