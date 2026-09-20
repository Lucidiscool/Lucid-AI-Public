"""Continue base-language training; stop for review before any chat tuning."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    lock = ROOT / "runs/base-expanded.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        output = ROOT / "checkpoints/base-expanded"
        latest = output / "latest.pt"
        command = [sys.executable, "-u", "train.py", "pretrain", "--data", "data/base-expanded",
                   "--out", str(output), "--device", "directml", "--steps", "10000",
                   "--batch-size", "1", "--accumulation", "4", "--lr", "0.0001",
                   "--warmup", "200", "--eval-every", "250", "--eval-batches", "32",
                   "--seed", "918", "--max-run-minutes", "90",
                   "--stop-file", str(ROOT / "PAUSE_BASE_LEARNING")]
        command += ["--resume", str(latest)] if latest.exists() else ["--init", "checkpoints/learning-pretrain/best.pt"]
        subprocess.run(command, cwd=ROOT, check=True)
        state = json.loads((output / "status.json").read_text(encoding="utf-8"))["state"]
        if state != "completed":
            print("Base training paused safely. Remove PAUSE_BASE_LEARNING if present and rerun this script to resume.", flush=True)
            return
        report = ROOT / "runs/base-expanded-after.json"
        if not report.exists():
            subprocess.run([sys.executable, "evaluate_base.py", "--checkpoint", str(output / "best.pt"),
                            "--out", str(report)], cwd=ROOT, check=True)
        print("Base run complete. Compare before/after reports before deciding on instruction tuning.", flush=True)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
