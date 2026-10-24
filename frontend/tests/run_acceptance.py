"""Run Vite, the real backend fixture and acceptance clients in one local process tree.
STRIDE_BACKEND_CHECKOUT must name the backend checkout. Its files are never edited.
PLAYWRIGHT_MODULE optionally names an installed Playwright ESM module.
"""
import os, subprocess, sys, time, urllib.request
from pathlib import Path
here = Path(__file__).resolve().parent.parent
backend = Path(os.environ['STRIDE_BACKEND_CHECKOUT']).resolve()
env = {**os.environ, 'PYTHONPATH': f'{backend / "backend_phase3"}:{here / "tests"}'}
from PIL import Image
import tempfile
with tempfile.TemporaryDirectory(prefix='stride-acceptance-') as temp:
    image = Path(temp) / 'test.jpeg'
    Image.new('RGB', (1,1)).save(image)
    env['TEST_JPEG'] = str(image)
    processes = []
    def start_backend():
        p = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend_fixture:app', '--host', '127.0.0.1', '--port', '8000'], cwd=here, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(p)
        wait('http://127.0.0.1:8000/health')
        return p
    def wait(url):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(url, timeout=1).close()
                return
            except Exception: time.sleep(.1)
        raise RuntimeError(f'Startup failed: {url}')
    try:
        vite = subprocess.Popen(['node', str(here / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1'], cwd=here, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(vite)
        server = start_backend()
        wait('http://127.0.0.1:8443/')
        subprocess.run(['node','--experimental-transform-types','tests/contract-live.ts'], cwd=here, env=env, check=True)
        server.terminate(); server.wait(timeout=10)
        start_backend()  # clean synthetic database for browser workflow
        subprocess.run(['node','tests/smoke.mjs'], cwd=here, env=env, check=True)
        subprocess.run(['node','tests/recovery.mjs'], cwd=here, env=env, check=True)
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill()
