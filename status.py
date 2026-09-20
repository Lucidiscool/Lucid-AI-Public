"""Read training progress without loading model weights or using the GPU."""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoints", default="checkpoints")
    args = parser.parse_args()
    paths = sorted(Path(args.checkpoints).glob("*/status.json"))
    if not paths:
        print("No tracked training runs yet.")
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        age = max(0, time.time() - row["updated_at"])
        state = row["state"]
        if state == "running" and age > 300:
            state += " (no update for over 5 minutes; check the training process)"
        loss = row.get("last_val_loss")
        loss_text = f"{loss:.4f}" if loss is not None else "not measured"
        print(f"{path.parent.name}: {state}")
        print(f"  {row['stage']} step {row['completed_step']}/{row['total_steps']} | "
              f"validation {loss_text} | {row['trained_tokens']:,} trained tokens")
        if row.get("error"):
            print(f"  Error: {row['error']}")


if __name__ == "__main__":
    main()
