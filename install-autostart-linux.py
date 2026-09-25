"""Install user services for the model, public host, and local browser app."""
import argparse
import getpass
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'runs/auto-update-state.json'


def quoted(value):
    return '"' + str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"') + '"'


def private_file(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-start', action='store_true', help='Enable services but let the operator stop existing manual hosts first')
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('Linux with systemd is required.')
    python = ROOT / '.venv/bin/python'
    if not python.exists() or not (ROOT / 'local_model.json').exists():
        parser.error('Install the Python environment and configure the local model first.')
    tools = ROOT / 'runtime/tools'
    environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get('PATH', os.defpath))
    gh = shutil.which('gh', path=environment['PATH'])
    if not gh or not shutil.which('cloudflared', path=environment['PATH']):
        parser.error('GitHub CLI and cloudflared are required.')
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    credentials = config / 'lucid-host/credentials'
    credentials.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials.chmod(0o700)
    saved = credentials / 'admin-passcode'
    password = os.environ.get('LUCID_ADMIN_PASSCODE')
    if password is None:
        password = saved.read_text().strip() if saved.exists() else getpass.getpass('Choose the Lucid admin passcode: ')
    if not 4 <= len(password) <= 512:
        parser.error('Admin passcode must contain 4–512 characters.')
    token = subprocess.run([gh, 'auth', 'token', '--hostname', 'github.com'],
                           env=environment, capture_output=True, text=True, check=True).stdout.strip()
    if not token:
        parser.error('Sign in with gh auth login first.')
    private_file(saved, password)
    private_file(credentials / 'github-token', token)
    (ROOT / 'runs').mkdir(exist_ok=True)
    if not STATE.exists():
        subprocess.run([str(python), str(ROOT / 'auto_update_linux.py'), '--initialize'],
                       cwd=ROOT, check=True)
    units = config / 'systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    for mode in ('model', 'host', 'local'):
        requirements = 'Wants=lucid-model.service\nAfter=lucid-model.service\n' if mode != 'model' else ''
        credential_lines = ''
        if mode == 'host':
            credential_lines = '\n'.join('LoadCredential=' + (name + ':' + str(credentials / name)).replace('%', '%%')
                                         for name in ('admin-passcode', 'github-token')) + '\n'
        service = (f'[Unit]\nDescription=Lucid {mode}\nPartOf=lucid.target\n'
                   f'StartLimitIntervalSec=0\n{requirements}\n[Service]\nType=simple\n'
                   f'WorkingDirectory={str(ROOT).replace(chr(37), chr(37) * 2)}\n'
                   f'Environment={quoted("PATH=" + environment["PATH"])}\n'
                   f'ExecStart={quoted(python)} {quoted(ROOT / "host_service.py")} {mode}\n'
                   f'{credential_lines}UMask=0077\nRestart=always\nRestartSec=20\n'
                   'KillMode=control-group\nTimeoutStopSec=30\n')
        (units / f'lucid-{mode}.service').write_text(service)
    (units / 'lucid.target').write_text(
        '[Unit]\nDescription=Lucid laptop hosting\n'
        'Wants=lucid-model.service lucid-host.service lucid-local.service\n'
        '\n[Install]\nWantedBy=default.target\n')
    (units / 'lucid-update.service').write_text(
        '[Unit]\nDescription=Refresh Lucid from GitHub and reload changed models\n'
        '\n[Service]\nType=oneshot\n'
        f'WorkingDirectory={str(ROOT).replace(chr(37), chr(37) * 2)}\n'
        f'Environment={quoted("PATH=" + environment["PATH"])}\n'
        f'ExecStart={quoted(python)} {quoted(ROOT / "auto_update_linux.py")}\n'
        'UMask=0077\n')
    (units / 'lucid-update.timer').write_text(
        '[Unit]\nDescription=Check for Lucid source and model updates\n\n'
        '[Timer]\nOnBootSec=2min\nOnUnitActiveSec=1min\n'
        'Persistent=true\nUnit=lucid-update.service\n\n'
        '[Install]\nWantedBy=timers.target\n')
    subprocess.run(['systemd-analyze', '--user', 'verify',
                    *[str(units / f'lucid-{mode}.service') for mode in ('model', 'host', 'local')],
                    str(units / 'lucid-update.service'), str(units / 'lucid-update.timer'),
                    str(units / 'lucid.target')], check=True)
    subprocess.run(['loginctl', 'enable-linger', getpass.getuser()], check=True)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', 'lucid.target'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'lucid-update.timer'], check=True)
    if not args.no_start:
        subprocess.run(['systemctl', '--user', 'restart', 'lucid.target'], check=True)
    print('Lucid autostart enabled at boot. Services retry if the network is unavailable.')
    print('Credentials are stored in owner-only files at ' + str(credentials))
    print('Stop: systemctl --user stop lucid.target')
    print('Restart: systemctl --user restart lucid.target')
    print('Update check: systemctl --user status lucid-update.timer')


if __name__ == '__main__':
    main()
