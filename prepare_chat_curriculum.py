"""A controlled concise-chat experiment using existing splits and tokenizer."""
import json
from pathlib import Path
import re
import shutil
import sqlite3
from prepare import valid_messages, digest
from tokenizer import encode_messages, load_tokenizer, fingerprint
from compare_models import PROMPTS

ROOT = Path(__file__).resolve().parent


def main():
    original = ROOT / "data/prepared"
    output = ROOT / "data/chat-curriculum"
    output.mkdir(exist_ok=False)
    tokenizer = load_tokenizer(original / "tokenizer.json")
    review = json.loads((ROOT / "runs/learning-review.json").read_text())
    banned = {digest(p) for p in PROMPTS}
    banned.update(digest(r["prompt"]) for r in review["results"])
    banned.update(map(digest, ["My favorite color is green.", "What is my favorite color?"]))
    selected = set()
    for path in [ROOT.parent / "lucidai_v3/data/chat/lucidai_chats.jsonl", ROOT / "examples/english_chat.jsonl"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            messages = valid_messages(json.loads(line))
            if path.name == "lucidai_chats.jsonl" and re.search(r"\d", str(messages)):
                continue
            if any(digest(m["content"]) in banned for m in messages if m["role"] == "user"):
                continue
            selected.add(digest(json.dumps(messages, ensure_ascii=False)))
    counts = {}
    with sqlite3.connect(original / "records.sqlite") as db:
        for split in ("train", "val"):
            rows = []
            for key, body in db.execute("SELECT key,body FROM records WHERE kind='chat' AND split=? ORDER BY key", (split,)):
                if key in selected:
                    ids, labels = encode_messages(tokenizer, json.loads(body))
                    if len(ids) <= 257:
                        rows.append({"ids": ids, "labels": labels})
            if not rows:
                raise ValueError("Curriculum needs both training and validation examples.")
            (output / f"chat_{split}.jsonl").write_text("\n".join(map(json.dumps, rows)) + "\n")
            counts[split] = len(rows)
    shutil.copy2(original / "tokenizer.json", output / "tokenizer.json")
    metadata = {"format_version": 1, "tokenizer_sha256": fingerprint(output / "tokenizer.json"),
                "files": {f"chat_{s}.jsonl": fingerprint(output / f"chat_{s}.jsonl") for s in ("train", "val")},
                "counts": counts, "parent_metadata_sha256": fingerprint(original / "metadata.json"),
                "note": "SFT-only subset; original splits preserved. Existing nonnumeric chat plus English seed; exact review prompts excluded. Not a broad assistant corpus."}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
