"""Entry points for the Linux user services; credentials stay on the host."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    mode = sys.argv[1]
    os.chdir(ROOT)
    if mode == 'model':
        from local_chat import Backend
        backend = Backend()
        command = backend.server_command()
        backend.client.close()
    elif mode == 'host':
        credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
        os.environ['LUCID_ADMIN_PASSCODE'] = (credentials / 'admin-passcode').read_text().strip()
        os.environ['GH_TOKEN'] = (credentials / 'github-token').read_text().strip()
        os.environ['GIT_TERMINAL_PROMPT'] = '0'
        command = [sys.executable, '-u', str(ROOT / 'host_public.py'),
                   '--unattended', '--external-model', '--publish']
    elif mode == 'local':
        command = [sys.executable, '-u', str(ROOT / 'website_server.py'), '--no-open']
    else:
        raise SystemExit('Expected model, host, or local.')
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
