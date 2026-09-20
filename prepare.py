"""Build deduplicated data, train a tokenizer and write portable training arrays."""
import argparse
from contextlib import closing
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import shutil
import unicodedata
import numpy as np
from tokenizer import encode_messages, encode_text, fingerprint, train_tokenizer, load_tokenizer
from splits import SplitPlanner


def normalize(text):
    return unicodedata.normalize("NFC", text).replace("\x00", "").replace("\r\n", "\n").strip()


def digest(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().casefold().encode()).hexdigest()


def split_for(key, validation_fraction=0.05):
    return "val" if int(key[:8], 16) / 2**32 < validation_fraction else "train"


def valid_messages(record):
    if "messages" not in record and "user" in record and "assistant" in record:
        record = {"messages": [{"role": "user", "content": record["user"]},
                               {"role": "assistant", "content": record["assistant"]}]}
    messages = record.get("messages", [])
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError("Expected messages or user/assistant fields.")
    cleaned, expected = [], "user"
    for index, message in enumerate(messages):
        role, content = message.get("role"), message.get("content")
        if not isinstance(content, str) or not normalize(content):
            raise ValueError("Message content must be nonempty text.")
        if index == 0 and role == "system":
            pass
        elif role != expected:
            raise ValueError("Messages must alternate user and assistant after an optional system message.")
        else:
            expected = "assistant" if role == "user" else "user"
        cleaned.append({"role": role, "content": normalize(content)})
    if cleaned[-1]["role"] != "assistant":
        raise ValueError("Training conversations must end with an assistant answer.")
    return cleaned


def json_lines(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("Expected a JSON object")
                    yield record
                except (ValueError, TypeError) as error:
                    raise ValueError(f"{path}:{line_number}: {error}") from error


def text_documents(path):
    # Plain text has no reliable story boundaries; blank-line paragraphs are units.
    paragraph = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                paragraph.append(line)
            elif paragraph:
                yield normalize("".join(paragraph))
                paragraph = []
        if paragraph:
            yield normalize("".join(paragraph))


def build(args):
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"Output directory must be empty: {output}. Use a new --out directory.")
    if not 0 < args.validation_fraction < 0.5 or args.vocab_size < 263:
        raise ValueError("Use a validation fraction between 0 and 0.5 and vocabulary >= 263.")
    texts, chats, documents = list(args.text), list(args.chat), list(args.documents)
    if args.v3:
        v3 = Path(args.v3)
        texts.append(str(v3 / "data/pretrain/pretrain.txt"))
        chats.extend(str(v3 / relative) for relative in (
            "data/instruction/instructions.jsonl", "data/chat/lucidai_chats.jsonl"))
    counts = Counter()
    planner = SplitPlanner(args.validation_fraction)
    db = sqlite3.connect(output / "records.sqlite")
    db.execute("CREATE TABLE records (kind TEXT, key TEXT, split TEXT, body TEXT, PRIMARY KEY(kind,key))")

    def add(kind, body, group=None, explicit_split=None, prompt=None):
        key = digest(body)
        links = []
        if group is not None:
            links.append("group:" + digest(str(group)))
        if prompt is not None:
            links.append("prompt:" + digest(prompt))
        planner.add(kind + ":" + key, links, explicit_split)
        split = "pending"
        cursor = db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?,?)", (kind, key, split, body))
        counts[f"{kind}_{split}" if cursor.rowcount else f"{kind}_duplicates"] += 1

    def add_document(text, group=None, explicit_split=None):
        text = normalize(text)
        if len(text) < 80 or sum(c.isalpha() for c in text) / max(len(text), 1) < 0.45:
            counts["documents_filtered"] += 1
        else:
            add("text", text, group, explicit_split)

    for path in texts:
        for text in text_documents(path):
            add_document(text)
    for path in documents:
        for record in json_lines(path):
            add_document(record["text"], record.get("group"), record.get("split"))
    for path in chats:
        for record in json_lines(path):
            try:
                messages = valid_messages(record)
            except (ValueError, AttributeError):
                counts["chat_filtered"] += 1
                continue
            # Group every continuation of the same opening question in one split.
            prompt = next(m["content"] for m in messages if m["role"] == "user")
            add("chat", json.dumps(messages, ensure_ascii=False), record.get("group"), record.get("split"), prompt)
    partitions = planner.resolve()
    rows = db.execute("SELECT kind,key FROM records").fetchall()
    db.executemany("UPDATE records SET split=? WHERE kind=? AND key=?",
                   ((partitions[kind + ":" + key], kind, key) for kind, key in rows))
    for kind in ("text", "chat"):
        counts.pop(kind + "_pending", None)
    for kind, split, count in db.execute("SELECT kind,split,COUNT(*) FROM records GROUP BY kind,split"):
        counts[f"{kind}_{split}"] = count
    db.commit()
    if any(counts[f"{kind}_{split}"] < 1 for kind in ("text", "chat") for split in ("train", "val")):
        db.close()
        raise ValueError("Need text and chat examples in BOTH splits. Add more varied data; use a new output directory.")

    def training_texts():
        # Successive serialized iterator reads can run on different tokenizer workers.
        # This reader is never shared with another iterator or used concurrently.
        with closing(sqlite3.connect(output / "records.sqlite", check_same_thread=False)) as reader:
            for kind, body in reader.execute("SELECT kind,body FROM records WHERE split='train' ORDER BY kind,key"):
                if kind == "text":
                    yield body
                else:
                    for message in json.loads(body):
                        yield message["content"]

    tokenizer_path = output / "tokenizer.json"
    existing_tokenizer = getattr(args, "tokenizer", None)
    if existing_tokenizer:
        tokenizer = load_tokenizer(existing_tokenizer)
        shutil.copy2(existing_tokenizer, tokenizer_path)
        print("Retaining the existing tokenizer for continued training.", flush=True)
    else:
        print("Training a fresh byte-level tokenizer on the training split...", flush=True)
        tokenizer = train_tokenizer(training_texts(), tokenizer_path, args.vocab_size)
    eos = tokenizer.token_to_id("<|eos|>")
    for split in ("train", "val"):
        with (output / f"pretrain_{split}.bin").open("wb") as stream:
            for (body,) in db.execute("SELECT body FROM records WHERE kind='text' AND split=? ORDER BY key", (split,)):
                ids = encode_text(tokenizer, body) + [eos]
                np.asarray(ids, dtype="<u4").tofile(stream)
                counts[f"pretrain_{split}_tokens"] += len(ids)
        with (output / f"chat_{split}.jsonl").open("w", encoding="utf-8") as stream:
            for (body,) in db.execute("SELECT body FROM records WHERE kind='chat' AND split=? ORDER BY key", (split,)):
                messages = json.loads(body)
                ids, labels = encode_messages(tokenizer, messages)
                stream.write(json.dumps({"ids": ids, "labels": labels}) + "\n")
    db.close()
    metadata = {"format_version": 1, "vocab_size": tokenizer.get_vocab_size(),
                "tokenizer_sha256": fingerprint(tokenizer_path), "binary_dtype": "<u4",
                "files": {name: fingerprint(output / name) for name in (
                    "pretrain_train.bin", "pretrain_val.bin", "chat_train.jsonl", "chat_val.jsonl")},
                "validation_fraction": args.validation_fraction, "counts": dict(counts),
                "sources": {"text": texts, "documents": documents, "chat": chats},
                "tokenizer_origin": str(existing_tokenizer) if existing_tokenizer else "trained_on_this_training_split",
                "split_note": "Connected groups, duplicate records and opening prompts stay together. Explicit train/val partitions are honored; validation wins conflicts. TXT split by paragraph."}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3", help="Import original text and chats from v3; never imports weights.")
    parser.add_argument("--text", action="append", default=[], help="UTF-8 text, blank-line paragraphs.")
    parser.add_argument("--documents", action="append", default=[], help='JSONL: {"text": "...", "group": "optional document ID"}')
    parser.add_argument("--chat", action="append", default=[], help="JSONL conversations.")
    parser.add_argument("--out", default="data/prepared")
    parser.add_argument("--vocab-size", type=int, default=16384)
    parser.add_argument("--tokenizer", help="Reuse an existing tokenizer for continued training without changing token IDs.")
    parser.add_argument("--validation-fraction", type=float, default=0.05)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
