"""Prepare balanced SFT data without changing the trained tokenizer."""
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import random
import re
import shutil
import sqlite3
from compare_models import PROMPTS
from prepare import digest, valid_messages
from splits import SplitPlanner
from tokenizer import encode_messages, fingerprint, load_tokenizer

ROOT = Path(__file__).resolve().parent
MIX = {"dialogue": .45, "writing": .15, "explanation": .20, "replay": .15, "technical": .05}


def category(messages):
    text = " ".join(m["content"] for m in messages if m["role"] == "user").lower()
    if re.search(r"\b(python|javascript|code|programming|linux|sql|html|algorithm)\b", text):
        return "technical"
    if len(messages) > 2:
        return "dialogue"
    if re.search(r"\b(write|rewrite|poem|story|sentence|summarize|grammar|punctuation|email)\b", text):
        return "writing"
    if re.search(r"\b(explain|why|how does|what is|what are|difference)\b", text):
        return "explanation"
    return "replay"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/dialogue-v2-reviewed")
    args = parser.parse_args()
    out = ROOT / args.out
    if out.exists():
        raise ValueError("Choose a new output; refusing to overwrite dialogue-v2.")
    tokenizer = load_tokenizer(ROOT / "data/prepared/tokenizer.json")
    planner, records, rejected = SplitPlanner(.1), {}, Counter()
    exclusions = json.loads((ROOT / "examples/dialogue_exclusions.json").read_text(encoding="utf-8"))
    excluded_groups = set()
    for path in (ROOT / "data/dialogue-sources").glob("oasst_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("source_id") in exclusions:
                excluded_groups.add(row["group"])
    banned = {digest(p) for p in PROMPTS}
    old_review = json.loads((ROOT / "runs/learning-review.json").read_text(encoding="utf-8"))
    banned.update(digest(r["prompt"]) for r in old_review["results"])
    banned.update(map(digest, ["My favorite color is green.", "What is my favorite color?"]))
    fresh = json.loads((ROOT / "examples/dialogue_holdout.json").read_text(encoding="utf-8"))
    banned.update(digest(m["content"]) for case in fresh for m in case["messages"] if m["role"] == "user")

    def add(record, source, fixed_split=None):
        messages = valid_messages(record)
        key = digest(json.dumps(messages, ensure_ascii=False))
        # Register all relationships before filtering to preserve split constraints.
        links = ["prompt:" + digest(m["content"]) for m in messages if m["role"] == "user"]
        if record.get("group"):
            links.append("group:" + str(record["group"]))
        planner.add(key, links, fixed_split or record.get("split"))
        if record.get("group") in excluded_groups:
            rejected["manual_review_group"] += 1
            return
        if any(digest(m["content"]) in banned for m in messages if m["role"] == "user"):
            rejected["evaluation_prompt"] += 1
            return
        joined = " ".join(m["content"] for m in messages).lower()
        if source == "oasst" and re.search(r"lyrics|openassistant|chatgpt|openai|as of 202|current president|latest news|i (?:have )?(?:searched|browsed)|i found (?:online|from a search)|past 24|last 30 days|https?://|updated my knowledge|never break character|act as a linux terminal", joined):
            rejected["source_scope_or_capability"] += 1
            return
        ids, labels = encode_messages(tokenizer, messages)
        if len(ids) > 257:
            rejected["over_context"] += 1
            return
        row = {"ids": ids, "labels": labels, "messages": messages, "key": key,
               "category": category(messages), "source": source,
               "group": record.get("group", key), "source_id": record.get("source_id"),
               "answer_tokens": sum(v != -100 for v in labels),
               "skill": record.get("category", "source_unclassified")}
        if key in records:
            rejected["duplicates"] += 1
        else:
            records[key] = row

    # Legacy split constraints apply even to records not selected for replay.
    with sqlite3.connect(ROOT / "data/prepared/records.sqlite") as db:
        for body, split in db.execute("SELECT body,split FROM records WHERE kind='chat'"):
            messages = json.loads(body)
            key = digest(json.dumps(messages, ensure_ascii=False))
            planner.add(key, ["prompt:" + digest(m["content"]) for m in messages if m["role"] == "user"], split)
    for split in ("validation", "train"):
        path = ROOT / f"data/dialogue-sources/oasst_{split}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            add(json.loads(line), "oasst")
    for line in (ROOT / "examples/dialogue_v2.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["group"] = "authored:" + row["group"]
        add(row, "assistant_authored")
    for line in (ROOT / "examples/english_chat.jsonl").read_text(encoding="utf-8").splitlines():
        add(json.loads(line), "legacy_english")
    # Limited replay from original source rows, not from generated model answers.
    legacy = ROOT.parent / "lucidai_v3/data/instruction/instructions.jsonl"
    pool = [json.loads(line) for line in legacy.read_text(encoding="utf-8").splitlines()]
    random.Random(73).shuffle(pool)
    for row in pool[:500]:
        add(row, "legacy_instruction")
    partitions = planner.resolve()
    # One complete path per OASST tree; prefer longer dialogue, then stable key.
    selected = {}
    for row in sorted(records.values(), key=lambda r: (-len(r["messages"]), r["key"])):
        group = row["group"] if row["source"] == "oasst" else row["key"]
        selected.setdefault(group, row)
    out.mkdir()
    report = {"rejected": dict(rejected), "mix_target_answer_tokens": MIX, "splits": {}}
    review_rows = []
    for split in ("train", "val"):
        rows = [r for r in selected.values() if partitions[r["key"]] == split]
        totals = Counter()
        for row in rows:
            totals[row["category"]] += row["answer_tokens"]
        if any(totals[c] == 0 for c in MIX):
            raise ValueError(f"Missing category in {split}: {totals}")
        for row in rows:
            row["split"] = split
            row["sampling_weight"] = MIX[row["category"]] / totals[row["category"]] if split == "train" else 1.0
        with (out / f"chat_{split}.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps({k:row[k] for k in ("ids", "labels", "sampling_weight")}) + "\n")
        (out / f"records_{split}.jsonl").write_text("\n".join(json.dumps({k:v for k,v in r.items() if k not in ("ids", "labels")}, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        report["splits"][split] = {"records": len(rows), "multi_turn": sum(len(r["messages"]) > 2 for r in rows),
            "category_records": dict(Counter(r["category"] for r in rows)), "category_answer_tokens": dict(totals),
            "source_records": dict(Counter(r["source"] for r in rows))}
        if split == "train":
            for name in MIX:
                options = [r for r in rows if r["category"] == name and r["source"] == "oasst"]
                review_rows.extend(options[:5])
    shutil.copy2(ROOT / "data/prepared/tokenizer.json", out / "tokenizer.json")
    (out / "review_sample.json").write_text(json.dumps(review_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report["tokenizer_sha256"] = fingerprint(out / "tokenizer.json")
    report["files"] = {f"chat_{s}.jsonl": fingerprint(out / f"chat_{s}.jsonl") for s in ("train", "val")}
    report["format_version"] = 1
    report["source_manifest_sha256"] = fingerprint(ROOT / "data/dialogue-sources/manifest.json")
    report["authored_sha256"] = fingerprint(ROOT / "examples/dialogue_v2.jsonl")
    report["manual_exclusions_sha256"] = fingerprint(ROOT / "examples/dialogue_exclusions.json")
    report["holdout_sha256"] = fingerprint(ROOT / "examples/dialogue_holdout.json")
    report["notes"] = ["SFT-only; original tokenizer retained.", "Weights target expected sampled answer-token shares, not guaranteed optimizer gradient shares.", "Validation is unweighted. Source categories are heuristic. Review labels do not establish factual correctness.", "Legacy held-out prompt constraints and official OASST partitions preserved; validation wins connections."]
    (out / "metadata.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
