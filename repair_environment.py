"""Refresh activation and console launchers after copying this development environment."""
import sys
import venv
from pathlib import Path
from importlib.metadata import entry_points
from pip._vendor.distlib.scripts import ScriptMaker

root = Path(__file__).resolve().parent
environment = root / '.venv-directml'
if Path(sys.prefix).resolve() != environment.resolve():
    raise SystemExit('Run using this folder\'s .venv-directml/Scripts/python.exe')
builder = venv.EnvBuilder()
context = builder.ensure_directories(str(environment))
builder.setup_scripts(context)
maker = ScriptMaker(None, str(environment / 'Scripts'))
maker.executable = str(environment / 'Scripts/python.exe')
maker.clobber = True
maker.variants = {''}
count = 0
for entry in entry_points(group='console_scripts'):
    maker.make(f'{entry.name} = {entry.value}')
    count += 1
print(f'Refreshed activation scripts and {count} console launchers for V5.')
