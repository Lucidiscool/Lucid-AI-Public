"""Validate the exact data artifacts used by the dialogue experiment."""
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
from prepare import digest
from tokenizer import fingerprint, load_tokenizer, encode_messages

ROOT = Path(__file__).resolve().parent


def main():
    directory = ROOT / "data/dialogue-v2-reviewed"
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    tokenizer = load_tokenizer(directory / "tokenizer.json")
    assert fingerprint(directory / "tokenizer.json") == metadata["tokenizer_sha256"]
    assert fingerprint(ROOT / "examples/dialogue_holdout.json") == metadata["holdout_sha256"]
    records, prompts = {}, {}
    shares = defaultdict(float)
    for split in ("train", "val"):
        assert fingerprint(directory / f"chat_{split}.jsonl") == metadata["files"][f"chat_{split}.jsonl"]
        records[split] = [json.loads(line) for line in (directory / f"records_{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        encoded = [json.loads(line) for line in (directory / f"chat_{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(records[split]) == len(encoded) == metadata["splits"][split]["records"]
        prompts[split] = {digest(m["content"]) for row in records[split] for m in row["messages"] if m["role"] == "user"}
        for row, tokens in zip(records[split], encoded):
            ids, labels = encode_messages(tokenizer, row["messages"])
            assert ids == tokens["ids"] and labels == tokens["labels"] and len(ids) <= 257
            assert tokens["sampling_weight"] == row["sampling_weight"] > 0
            if split == "train":
                shares[row["category"]] += row["sampling_weight"] * row["answer_tokens"]
            else:
                assert row["sampling_weight"] == 1
    assert not prompts["train"] & prompts["val"]
    assert not ({r["group"] for r in records["train"]} & {r["group"] for r in records["val"]})
    holdout = json.loads((ROOT / "examples/dialogue_holdout.json").read_text(encoding="utf-8"))
    reserved = {digest(m["content"]) for case in holdout for m in case["messages"] if m["role"] == "user"}
    assert not reserved & (prompts["train"] | prompts["val"])
    with sqlite3.connect(ROOT / "data/prepared/records.sqlite") as db:
        legacy_val = {digest(m["content"]) for (body,) in db.execute("SELECT body FROM records WHERE kind='chat' AND split='val'") for m in json.loads(body) if m["role"] == "user"}
    assert not legacy_val & prompts["train"]
    for key, target in metadata["mix_target_answer_tokens"].items():
        assert abs(shares[key] - target) < 1e-9
    result = {"passed": True, "checks": ["fingerprints", "encoded labels", "context limits", "prompt/group split separation", "legacy validation exclusion", "reserved prompt exclusion", "expected token mixture"], "expected_answer_token_shares": dict(shares)}
    (ROOT / "runs/dialogue-data-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
