"""Inspect actual saved training evidence and answer-token distribution."""
from collections import Counter
import json
from pathlib import Path
import torch
from tokenizer import load_tokenizer, encode_messages

ROOT = Path(__file__).resolve().parent


def main():
    tokenizer = load_tokenizer(ROOT / "data/prepared/tokenizer.json")
    sources = [ROOT.parent / "lucidai_v3/data/instruction/instructions.jsonl",
               ROOT.parent / "lucidai_v3/data/chat/lucidai_chats.jsonl", ROOT / "examples/english_chat.jsonl"]
    groups = {}
    for path in sources:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            category = record.get("source", path.stem)
            messages = record.get("messages") or [{"role": "user", "content": record["user"]},
                                                     {"role": "assistant", "content": record["assistant"]}]
            ids, labels = encode_messages(tokenizer, messages)
            row = groups.setdefault(category, Counter())
            row["records"] += 1
            row["answer_tokens"] += sum(t != -100 for t in labels)
            row["multi_turn"] += len(messages) > 2
    checkpoints = {}
    for path in sorted((ROOT.parent / "lucidai_v3/checkpoints").glob("*best.pt")):
        saved = torch.load(path, map_location="cpu", weights_only=True)
        checkpoints[path.name] = {key: saved[key] for key in ("step", "best_validation_loss") if key in saved}
    report = {"source_counts_before_preparation_deduplication": groups, "v3_checkpoints": checkpoints,
              "v4_checkpoints": {}}
    for folder in ("improved-pretrain", "learning-pretrain", "sft", "learning-sft"):
        report["v4_checkpoints"][folder] = json.loads((ROOT / "checkpoints" / folder / "status.json").read_text())
    (ROOT / "runs/training-audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
