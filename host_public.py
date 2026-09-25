"""Run Lucid V5 behind a free temporary tunnel; optionally publish its address."""
import argparse
import getpass
import os
import json
import re
import subprocess
import sys
import time
from pathlib import Path
import httpx
from local_chat import Backend

ROOT = Path(__file__).resolve().parent
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Commit and push the new tunnel address to GitHub Pages')
    parser.add_argument('--admin', action='store_true', help='Prompt privately for the local admin passcode')
    args = parser.parse_args()
    if args.admin:
        password = getpass.getpass('Enter your admin passcode (input is hidden): ')
        if not 4 <= len(password) <= 512:
            parser.error('The admin passcode must contain 4–512 characters.')
        os.environ['LUCID_ADMIN_PASSCODE'] = password
    if not (ROOT / 'runtime/cloudflared.exe').is_file():
        raise RuntimeError('Missing runtime/cloudflared.exe. Install Cloudflare Tunnel from its official distribution before starting.')
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
    model.start()
    model.client.close()
    processes = []
    try:
        with (runs / 'public-gateway.log').open('w', encoding='utf-8') as gateway_log, (runs / 'public-tunnel.log').open('w', encoding='utf-8') as tunnel_log:
            gateway = subprocess.Popen([sys.executable, '-u', 'public_server.py'], cwd=ROOT, stdout=gateway_log, stderr=subprocess.STDOUT, creationflags=FLAGS)
            processes.append(gateway)
            for _ in range(30):
                try:
                    response = httpx.get('http://127.0.0.1:8767/api/health', headers={'Origin': 'https://lucidiscool.github.io'}, trust_env=False, timeout=2)
                    if response.json().get('app') == 'lucid-v5-public':
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('Public gateway did not start.')
            tunnel = subprocess.Popen([str(ROOT / 'runtime/cloudflared.exe'), 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8767', '--http-host-header', '127.0.0.1:8767'], cwd=ROOT, stdout=tunnel_log, stderr=subprocess.STDOUT, creationflags=FLAGS)
            processes.append(tunnel)
            url = None
            for _ in range(90):
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
                (ROOT / 'website/backend.json').write_text(json.dumps({'provider': 'local', 'url': url}, indent=2)+'\n', encoding='utf-8')
                for command in [ ['rtk','git','add','website/backend.json'],
                                 ['rtk','git','commit','--only','website/backend.json','-m','Connect website to running Lucid V5 host'],
                                 ['rtk','git','push','origin','main'] ]:
                    subprocess.run(command, cwd=ROOT, check=True)
            print('Lucid V5 is available through '+url, flush=True)
            print('The website is configured with this PC tunnel address.', flush=True)
            print('Keep this process and your PC running. Use stop-public.cmd to stop sharing.', flush=True)
            (runs / 'public-host.json').write_text(json.dumps({'url': url, 'gateway_pid': gateway.pid, 'tunnel_pid': tunnel.pid}), encoding='utf-8')
            while not stop.exists():
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('A public hosting process stopped. Restart start-public.cmd.')
                time.sleep(2)
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    main()
