"""Refresh a Linux Lucid host after upstream code or local model changes."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'
STATE = RUNS / 'auto-update-state.json'
LOCK = RUNS / 'repo-update.lock'


def run(*args, check=True, capture_output=True):
    return subprocess.run(args, cwd=ROOT, check=check, text=True,
                          capture_output=capture_output)


def model_signature():
    config_path = ROOT / 'local_model.json'
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    model = Path(config['model']).expanduser()
    try:
        stat = model.stat()
        model_stat = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]
    except OSError:
        model_stat = None
    return [hashlib.sha256(config_bytes).hexdigest(), str(model), model_stat]


def local_source_signature():
    diff = run('git', 'diff', '--binary', 'HEAD').stdout
    return hashlib.sha256(diff.encode()).hexdigest()


def local_requirements_signature():
    diff = run('git', 'diff', '--binary', 'HEAD', '--',
               'requirements-web.txt', 'requirements.txt').stdout
    return hashlib.sha256(diff.encode()).hexdigest()


def needs_service_restart(paths):
    return any(path in ('requirements-web.txt', 'requirements.txt')
               or (Path(path).parent == Path('.') and Path(path).suffix == '.py')
               for path in paths)


def initialize():
    RUNS.mkdir(exist_ok=True)
    head = run('git', 'rev-parse', 'HEAD').stdout.strip()
    signature = model_signature()
    STATE.write_text(json.dumps({'applied_source': head, 'requirements_source': head,
                                 'applied_working': local_source_signature(),
                                 'requirements_working': local_requirements_signature(),
                                 'applied_model': signature,
                                 'pending_model': None}, indent=2) + '\n')


def restart_services(state, source):
    print('Restarting Lucid services to load the update.', flush=True)
    subprocess.run(['systemctl', '--user', 'restart', 'lucid.target'], check=True)
    state['applied_source'] = source
    state['applied_model'] = model_signature()
    state['pending_model'] = None
    state['applied_working'] = local_source_signature()
    state['pending_working'] = None
    STATE.write_text(json.dumps(state, indent=2) + '\n')


def observe_model(state, signature):
    if 'applied_model' not in state:
        state.update(applied_model=signature, pending_model=None)
        return False
    if signature == state['applied_model']:
        state['pending_model'] = None
        return False
    pending = state.get('pending_model')
    now = time.time()
    if not pending or pending.get('signature') != signature:
        state['pending_model'] = {'signature': signature, 'since': now}
        return False
    if now - pending['since'] < 45:
        return False
    state.update(applied_model=signature, pending_model=None)
    print('Local model configuration or model file changed.', flush=True)
    return True


def observe_working_changes(state, signature):
    if 'applied_working' not in state:
        state['applied_working'] = signature
        state['pending_working'] = None
        return False
    if signature == state['applied_working']:
        state['pending_working'] = None
        return False
    pending = state.get('pending_working')
    now = time.time()
    if not pending or pending.get('signature') != signature:
        state['pending_working'] = {'signature': signature, 'since': now}
        return False
    if now - pending['since'] < 45:
        return False
    print('Local Lucid source files changed.', flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    RUNS.mkdir(exist_ok=True)
    if args.initialize:
        initialize()
        return

    with LOCK.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if not all(subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0
                   for unit in ('lucid-model', 'lucid-host', 'lucid-local')):
            return
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        restart = observe_model(state, model_signature())
        restart = observe_working_changes(state, local_source_signature()) or restart
        old_head = run('git', 'rev-parse', 'HEAD').stdout.strip()
        applied_head = state.get('applied_source')
        if applied_head not in (None, old_head):
            ancestry = subprocess.run(['git', 'merge-base', '--is-ancestor', applied_head, old_head], cwd=ROOT)
            if ancestry.returncode != 0:
                restart = True
            else:
                already_applied = run('git', 'diff', '--name-only', applied_head, old_head).stdout.splitlines()
                restart = needs_service_restart(already_applied) or restart
        STATE.write_text(json.dumps(state, indent=2) + '\n')
        try:
            run('git', 'fetch', '--quiet', 'origin', 'main')
        except subprocess.CalledProcessError:
            print('GitHub is unavailable; the next timer will retry.', flush=True)
            if restart:
                restart_services(state, old_head)
            return
        new_head = run('git', 'rev-parse', 'origin/main').stdout.strip()
        if new_head != old_head:
            ancestry = subprocess.run(['git', 'merge-base', '--is-ancestor', old_head, new_head], cwd=ROOT)
            if ancestry.returncode != 0:
                print('Upstream changed, but the local branch is not a fast-forward; leaving files untouched.', flush=True)
                return
            status = run('git', 'status', '--porcelain', '--untracked-files=no').stdout
            if status:
                print('Local tracked edits are present; will retry the upstream refresh later.', flush=True)
                new_head = old_head
            else:
                changed = run('git', 'diff', '--name-only', old_head, new_head).stdout.splitlines()
                run('git', 'merge', '--ff-only', new_head)
                print('Updated Lucid source to ' + new_head[:12] + '.', flush=True)
                restart = needs_service_restart(changed) or restart

        requirements_source = state.get('requirements_source', old_head)
        if requirements_source != new_head:
            changed = run('git', 'diff', '--name-only', requirements_source, new_head).stdout.splitlines()
            if any(name in ('requirements-web.txt', 'requirements.txt') for name in changed):
                run(sys.executable, '-m', 'pip', 'install', '-r', 'requirements-web.txt', capture_output=False)
            state['requirements_source'] = new_head
        local_changes = run('git', 'diff', '--name-only', 'HEAD').stdout.splitlines()
        local_req_sig = local_requirements_signature()
        if (any(name in ('requirements-web.txt', 'requirements.txt') for name in local_changes)
                and state.get('requirements_working') != local_req_sig):
            run(sys.executable, '-m', 'pip', 'install', '-r', 'requirements-web.txt', capture_output=False)
        state['requirements_working'] = local_req_sig

        if restart:
            restart_services(state, new_head)
        else:
            state['applied_source'] = new_head
            STATE.write_text(json.dumps(state, indent=2) + '\n')


if __name__ == '__main__':
    main()
