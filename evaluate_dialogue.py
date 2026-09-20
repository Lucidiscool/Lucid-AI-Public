"""Fixed-prompt dialogue regression review. Never a training data source."""
import argparse
import json
from pathlib import Path
import torch
from chat import ChatSession
from tokenizer import fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(1337)
    path = Path("examples/dialogue_holdout.json")
    cases = json.loads(path.read_text(encoding="utf-8"))
    session = ChatSession(args.checkpoint, args.device)
    results = []
    for case in cases:
        session.history = [dict(m) for m in case["messages"][:-1]]
        answer, ended = session.answer(case["messages"][-1]["content"], max_new_tokens=64, temperature=0)
        results.append({**case, "answer": answer, "ended_naturally": ended, "review_score": None})
        print(f"{case['id']}: {answer}", flush=True)
    with Path(args.out).open("x", encoding="utf-8") as stream:
        json.dump({"checkpoint": str(Path(args.checkpoint).resolve()), "step": session.step,
                   "holdout_sha256": fingerprint(path), "decoding": "greedy, repetition penalty 1.1, 64 new tokens",
                   "note": "Context cases supply a fixed assistant history; not a free-running conversation test. Scores require review.",
                   "results": results}, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
