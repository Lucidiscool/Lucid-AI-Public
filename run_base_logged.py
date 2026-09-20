"""Run or resume the base experiment while appending to its live log."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == "__main__":
    with (ROOT / "runs/base-expanded.log").open("ab", buffering=0) as output, \
            (ROOT / "runs/base-expanded-errors.log").open("ab", buffering=0) as errors:
        output.write(b"\nResuming base experiment from the latest saved checkpoint.\n")
        result = subprocess.run([sys.executable, "-u", "learn_base_expanded.py"],
                                cwd=ROOT, stdout=output, stderr=errors)
        raise SystemExit(result.returncode)
