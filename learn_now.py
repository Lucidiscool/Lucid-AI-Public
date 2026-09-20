"""Bounded two-stage learning run; old checkpoints remain available."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STOP = ROOT / "PAUSE_LEARNING"


def run(stage, output, source, steps, lr, minutes):
    folder = ROOT / output
    command = [sys.executable, "train.py", stage, "--device", "directml",
               "--data", "data/prepared", "--out", output,
               "--steps", str(steps), "--lr", lr, "--warmup", "200",
               "--batch-size", "1", "--accumulation", "4", "--seed", "2026",
               "--eval-every", "250", "--eval-batches", "32",
               "--max-run-minutes", str(minutes), "--stop-file", str(STOP)]
    latest = folder / "latest.pt"
    command += ["--resume", str(latest)] if latest.exists() else ["--init", source]
    subprocess.run(command, cwd=ROOT, check=True)
    return json.loads((folder / "status.json").read_text())["state"] == "completed"


if __name__ == "__main__":
    if run("pretrain", "checkpoints/learning-pretrain", "checkpoints/improved-pretrain/best.pt",
           10000, "0.00015", 90):
        if not STOP.exists() and run("sft", "checkpoints/learning-sft", "checkpoints/learning-pretrain/best.pt",
                                    2000, "0.00005", 30):
            report = ROOT / "runs/learning-review.json"
            if not report.exists():
                subprocess.run([sys.executable, "evaluate.py", "--checkpoint",
                                "checkpoints/learning-sft/best.pt", "--device", "directml",
                                "--max-new-tokens", "64", "--out", str(report)], cwd=ROOT, check=True)
            print("Learning finished. Review runs/learning-review.json before selecting the new model.", flush=True)
    else:
        print("Learning paused. Run learn_now.py again to resume with the same schedule.", flush=True)
