"""Run Lucid V5 behind a free temporary tunnel; optionally publish its address."""
import argparse
from contextlib import contextmanager
import getpass
import os
import json
import re
import subprocess
import sys
import time
import shutil
import signal
from pathlib import Path
import httpx
from local_chat import Backend

ROOT = Path(__file__).resolve().parent
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


@contextmanager
def repository_update_lock(path):
    path.parent.mkdir(exist_ok=True)
    with path.open('a') as lock:
        if sys.platform.startswith('linux'):
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform.startswith('linux'):
                fcntl.flock(lock, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Commit and push the new tunnel address to GitHub Pages')
    parser.add_argument('--admin', action='store_true', help='Prompt privately for the local admin passcode')
    parser.add_argument('--unattended', action='store_true', help='Require the admin passcode from the service environment')
    parser.add_argument('--external-model', action='store_true', help='Wait for a separately supervised model server')
    args = parser.parse_args()
    if args.admin or args.unattended:
        password = os.environ.get('LUCID_ADMIN_PASSCODE', '') if args.unattended else getpass.getpass('Enter your admin passcode (input is hidden): ')
        if not 4 <= len(password) <= 512:
            parser.error('The admin passcode must contain 4–512 characters.')
        os.environ['LUCID_ADMIN_PASSCODE'] = password
    tunnel_binary = shutil.which('cloudflared')
    if not tunnel_binary:
        bundled_tunnel = ROOT / 'runtime' / ('cloudflared.exe' if os.name == 'nt' else 'cloudflared')
        if bundled_tunnel.is_file():
            tunnel_binary = str(bundled_tunnel)
    if not tunnel_binary:
        raise RuntimeError('cloudflared is missing. Install Cloudflare Tunnel and make sure it is on PATH.')
    config_path = ROOT / 'website/backend.json'
    runs = ROOT / 'runs'
    runs.mkdir(exist_ok=True)
    stop = runs / 'stop-public'
    stop.unlink(missing_ok=True)
    # Fail before creating a second tunnel if the gateway port is already occupied.
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8767)) == 0:
            raise RuntimeError('The public gateway is already running on port 8767.')
    model = Backend()
    print('Starting your existing Lucid V5 model...', flush=True)
    if args.external_model:
        for _ in range(180):
            if model.ready():
                break
            time.sleep(1)
        else:
            raise RuntimeError('Supervised model did not become ready.')
    else:
        model.start()
    processes = []
    try:
        with (runs / 'public-gateway.log').open('w', encoding='utf-8') as gateway_log, (runs / 'public-tunnel.log').open('w', encoding='utf-8') as tunnel_log:
            gateway = subprocess.Popen([sys.executable, '-u', 'public_server.py'], cwd=ROOT, stdout=gateway_log, stderr=subprocess.STDOUT, creationflags=FLAGS)
            processes.append(gateway)
            for _ in range(30):
                if gateway.poll() is not None:
                    raise RuntimeError('Public gateway stopped; inspect runs/public-gateway.log.')
                try:
                    response = httpx.get('http://127.0.0.1:8767/api/health', headers={'Origin': 'https://lucidiscool.github.io'}, trust_env=False, timeout=2)
                    if response.json().get('app') == 'lucid-v5-public':
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('Public gateway did not start.')
            tunnel = subprocess.Popen([tunnel_binary, 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8767', '--http-host-header', '127.0.0.1:8767'], cwd=ROOT, stdout=tunnel_log, stderr=subprocess.STDOUT, creationflags=FLAGS)
            processes.append(tunnel)
            url = None
            for _ in range(180):
                log = (runs / 'public-tunnel.log').read_text(encoding='utf-8', errors='replace')
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', log)
                if match:
                    url = match.group()
                    try:
                        response = httpx.get(url+'/api/health', headers={'Origin': 'https://lucidiscool.github.io'}, timeout=5)
                        if response.status_code == 200 and response.json().get('app') == 'lucid-v5-public':
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                if tunnel.poll() is not None:
                    raise RuntimeError('Tunnel stopped; inspect runs/public-tunnel.log.')
                time.sleep(1)
            else:
                raise RuntimeError('Tunnel did not become reachable.')
            if args.publish:
                with repository_update_lock(runs / 'repo-update.lock'):
                    (ROOT / 'website/backend.json').write_text(json.dumps({'provider': 'local', 'url': url}, indent=2)+'\n', encoding='utf-8')
                    commands = []
                    changed = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'website/backend.json'], cwd=ROOT)
                    if changed.returncode == 1:
                        commands = [['git','add','website/backend.json'],
                                    ['git','commit','--only','website/backend.json','-m','Connect website to running Lucid V5 host']]
                    elif changed.returncode != 0:
                        raise RuntimeError('Could not inspect website backend configuration.')
                    for command in commands + [['git','push','origin','main']]:
                        subprocess.run(command, cwd=ROOT, check=True)
            print('Lucid V5 is available through '+url, flush=True)
            print('The website is configured with this PC tunnel address.', flush=True)
            print('Keep this process and your PC running. Use stop-public.cmd to stop sharing.', flush=True)
            (runs / 'public-host.json').write_text(json.dumps({'url': url, 'gateway_pid': gateway.pid, 'tunnel_pid': tunnel.pid}), encoding='utf-8')
            while not stop.exists():
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('A public hosting process stopped. Restart start-public.cmd.')
                if not model.ready():
                    raise RuntimeError('Model stopped; restarting the host is required.')
                time.sleep(2)
    finally:
        model.client.close()
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    def shutdown(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)
    try:
        main()
    except KeyboardInterrupt:
        pass
