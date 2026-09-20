"""Collect a bounded, revision-pinned English corpus; never download model weights.

Requires httpx and pyarrow. Outputs document/conversation JSONL plus provenance.
Run with the isolated DirectML Python: python collect_data.py --out data/expanded_sources
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata


SOURCES = {
    "tinystories": {"repo": "roneneldan/TinyStories", "revision": "f54c09fd23315a6f9c86f9dc80f725de7d8f9c64", "license": "CDLA-Sharing-1.0", "synthetic": True},
    "cosmopedia": {"repo": "HuggingFaceTB/cosmopedia", "revision": "0ae6ec63f91742bd2d1eaef4f02232c55d719385", "license": "Apache-2.0", "synthetic": True},
    "dolly": {"repo": "databricks/databricks-dolly-15k", "revision": "bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a", "license": "CC-BY-SA-3.0", "synthetic": False},
    "oasst": {"repo": "OpenAssistant/oasst1", "revision": "fdf72ae0827c1cda404aff25b6603abec9e3399b", "license": "Apache-2.0", "synthetic": False},
}
OASST_FILES = {"train": "data/train-00000-of-00001-b42a775f407cee45.parquet", "validation": "data/validation-00000-of-00001-134b8fd0c89408b6.parquet"}
COSMOPEDIA_FILES = {"khanacademy": "data/khanacademy/train-00000-of-00001.parquet", "openstax": "data/openstax/train-00000-of-00002.parquet"}


def normalize(text):
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\x00", "").strip()


def digest(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().casefold().encode("utf-8")).hexdigest()


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def clean_prose(text, minimum=120):
    if not isinstance(text, str):
        return None
    text = normalize(text)
    if not minimum <= len(text) <= 60000 or "\ufffd" in text or "<|" in text:
        return None
    if sum(c.isalpha() for c in text) / len(text) < 0.5:
        return None
    # Sources specify English; this catches badly encoded or mismatched rows.
    letters = [c for c in text if c.isalpha()]
    if sum(c.isascii() for c in letters) / max(len(letters), 1) < 0.94:
        return None
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 20]
    if len(lines) >= 6 and len(set(lines)) / len(lines) < 0.7:
        return None
    if re.search(r"(.)\1{24,}", text):
        return None
    return text


def complete_stories(raw):
    """Never emit the final partial story from a byte-capped prefix."""
    for story in raw.decode("utf-8", errors="replace").split("<|endoftext|>")[:-1]:
        text = clean_prose(story)
        if text:
            yield text


def conversation_ok(messages, max_chars=3800):
    if len(messages) < 2 or len(messages) % 2:
        return False
    if sum(len(m["content"]) for m in messages) > max_chars:
        return False
    for index, message in enumerate(messages):
        text = message["content"]
        if message["role"] != ("user" if index % 2 == 0 else "assistant"):
            return False
        if not text or "\ufffd" in text or "<|" in text or re.search(r"(.)\1{24,}", text):
            return False
        letters = [c for c in text if c.isalpha()]
        if letters and sum(c.isascii() for c in letters) / len(letters) < 0.94:
            return False
    return True


def dolly_conversation(row, max_chars=3800):
    instruction = normalize(row.get("instruction", ""))
    answer = normalize(row.get("response", ""))
    context = normalize(row.get("context", ""))
    # The publisher recommends removing Wikipedia citation-number artifacts.
    context = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", context)
    question = instruction + ("\n\nContext:\n" + context if context else "")
    messages = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return messages if instruction and conversation_ok(messages, max_chars) else None


def oasst_labels(row):
    labels = row.get("labels") or {}
    if "name" in labels:
        return dict(zip(labels["name"], labels["value"]))
    return {name: value.get("value", 0) if isinstance(value, dict) else value for name, value in labels.items()}


def oasst_usable(row):
    if row.get("lang") != "en" or row.get("deleted") or row.get("review_result") is not True:
        return False
    if row.get("synthetic"):
        return False
    labels = oasst_labels(row)
    for key in ("spam", "lang_mismatch", "pii", "not_appropriate", "hate_speech", "sexual_content", "fails_task"):
        if labels.get(key, 0) > 0.2:
            return False
    if labels.get("quality", 1) < 0.5 or labels.get("toxicity", 0) > 0.5:
        return False
    return row.get("role") != "assistant" or row.get("rank") in (0, 1)


def oasst_conversations(rows, max_chars=3800):
    """Complete root-to-answer paths; all branches share the same root group."""
    by_id = {row["message_id"]: row for row in rows}
    for row in rows:
        if row.get("role") != "assistant" or not oasst_usable(row):
            continue
        path, seen, current = [], set(), row
        while current is not None:
            ident = current["message_id"]
            if ident in seen or not oasst_usable(current):
                path = []
                break
            seen.add(ident)
            path.append(current)
            parent_id = current.get("parent_id")
            if parent_id is not None and parent_id not in by_id:
                path = []
                break
            current = by_id.get(parent_id)
        if not path:
            continue
        path.reverse()
        messages = [{"role": "user" if r["role"] == "prompter" else "assistant", "content": normalize(r["text"])} for r in path]
        if conversation_ok(messages, max_chars):
            yield path[0]["message_id"], row["message_id"], messages


def cosmopedia_group(row):
    """Group alternate styles from the same quoted seed whenever available."""
    prompt = normalize(row.get("prompt", ""))
    quoted = re.findall(r'"([^"\n]{30,}(?:\n[^"\n]*)*)"', prompt)
    seed = max(quoted, key=len) if quoted else prompt
    return "cosmopedia:" + digest(seed)


class Collector:
    def __init__(self, out, max_chat_chars):
        import httpx
        self.out = Path(out).resolve()
        self.cache = self.out / "raw"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=30))
        self.max_chat_chars = max_chat_chars
        self.assets = []
        self.outputs = {}
        self.seen_text = set()
        self.seen_chat = set()

    def download(self, source, filename, prefix_bytes=None):
        spec = SOURCES[source]
        url = f"https://huggingface.co/datasets/{spec['repo']}/resolve/{spec['revision']}/{filename}"
        name = source + "__" + filename.replace("/", "__")
        if prefix_bytes:
            name += f".prefix-{prefix_bytes}"
        target = self.cache / name
        sidecar = target.with_name(target.name + ".json")
        if target.exists() and sidecar.exists():
            record = json.loads(sidecar.read_text(encoding="utf-8"))
            if record["url"] == url and record["sha256"] == file_hash(target):
                self.assets.append(record)
                print(f"Using verified cache: {name}", flush=True)
                return target
        partial = target.with_name(target.name + ".partial")
        cap = prefix_bytes or 350_000_000
        for attempt in range(3):
            try:
                count, next_progress = 0, 20_000_000
                headers = {"Range": f"bytes=0-{prefix_bytes - 1}"} if prefix_bytes else {}
                print(f"Downloading {name} (cap {cap / 1e6:.1f} MB)", flush=True)
                with self.client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    with partial.open("wb") as stream:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if count + len(chunk) > cap:
                                if prefix_bytes:
                                    chunk = chunk[:cap - count]
                                else:
                                    raise ValueError(f"Download exceeded cap for {url}")
                            stream.write(chunk)
                            count += len(chunk)
                            if count >= next_progress:
                                print(f"  {count / 1e6:.1f} MB received", flush=True)
                                next_progress += 20_000_000
                            if prefix_bytes and count >= cap:
                                break
                if count == 0:
                    raise ValueError(f"Empty download: {url}")
                partial.replace(target)
                record = {"url": url, "path": str(target.relative_to(self.out)), "bytes": count,
                          "sha256": file_hash(target), "prefix_bytes": prefix_bytes,
                          "source": source, "revision": spec["revision"]}
                sidecar.write_text(json.dumps(record, indent=2), encoding="utf-8")
                self.assets.append(record)
                return target
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    def metadata(self, source, source_split, ident, group, split=None):
        spec = SOURCES[source]
        record = {"source": spec["repo"], "source_revision": spec["revision"], "source_split": source_split,
                  "source_id": str(ident), "license": spec["license"], "synthetic": spec["synthetic"], "group": group}
        if split:
            record["split"] = split
        return record

    def write(self, name, records, kind, limit_bytes=None):
        target = self.out / name
        partial = target.with_name(target.name + ".partial")
        counts, text_bytes = Counter(), 0
        with partial.open("w", encoding="utf-8", newline="\n") as stream:
            for row in records:
                body = row["text"] if kind == "documents" else json.dumps(row["messages"], ensure_ascii=False)
                key = digest(body)
                seen = self.seen_text if kind == "documents" else self.seen_chat
                if key in seen:
                    counts["duplicates"] += 1
                    continue
                size = len(body.encode("utf-8"))
                if limit_bytes and text_bytes + size > limit_bytes:
                    break
                seen.add(key)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts["records"] += 1
                counts["split_" + row.get("split", "group_hash")] += 1
                if kind == "conversations" and len(row["messages"]) > 2:
                    counts["multi_turn"] += 1
                text_bytes += size
        partial.replace(target)
        self.outputs[name] = {"kind": kind, **counts, "text_bytes": text_bytes, "bytes": target.stat().st_size, "sha256": file_hash(target)}
        print(f"Ready {name}: {counts['records']:,} records, {text_bytes / 1e6:.1f} MB text", flush=True)

    def stories(self, split, raw_bytes):
        filename = "TinyStoriesV2-GPT4-" + ("valid" if split == "validation" else "train") + ".txt"
        path = self.download("tinystories", filename, raw_bytes)
        for index, text in enumerate(complete_stories(path.read_bytes())):
            row = self.metadata("tinystories", split, index, "tinystories:" + digest(text), "val" if split == "validation" else "train")
            yield {**row, "text": text}

    def education(self, subset):
        import pyarrow.parquet as pq
        path = self.download("cosmopedia", COSMOPEDIA_FILES[subset])
        parquet = pq.ParquetFile(path)
        index = 0
        for batch in parquet.iter_batches(batch_size=512):
            for row in batch.to_pylist():
                text = clean_prose(row["text"])
                if text:
                    meta = self.metadata("cosmopedia", f"{subset}/train", index, cosmopedia_group(row))
                    yield {**meta, "text": text}
                index += 1

    def dolly(self):
        path = self.download("dolly", "databricks-dolly-15k.jsonl")
        with path.open(encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                row = json.loads(line)
                messages = dolly_conversation(row, self.max_chat_chars)
                if messages:
                    group = "dolly:" + digest(row.get("context") or row["instruction"])
                    meta = self.metadata("dolly", "train", index, group)
                    yield {**meta, "messages": messages, "category": row.get("category")}

    def oasst(self, split):
        import pyarrow.parquet as pq
        path = self.download("oasst", OASST_FILES[split])
        rows = pq.read_table(path).to_pylist()
        for root_id, message_id, messages in oasst_conversations(rows, self.max_chat_chars):
            meta = self.metadata("oasst", split, message_id, "oasst:" + root_id, "val" if split == "validation" else "train")
            yield {**meta, "messages": messages}

    def run(self, story_mb=80, education_mb=110):
        # Read validation first so an exact duplicate is retained only as held out.
        self.write("stories_val.jsonl", self.stories("validation", 4_000_000), "documents")
        self.write("stories_train.jsonl", self.stories("train", int(story_mb * 1e6)), "documents")
        for subset, fraction in (("khanacademy", 0.4), ("openstax", 0.6)):
            self.write(f"education_{subset}.jsonl", self.education(subset), "documents", int(education_mb * fraction * 1e6))
        self.write("oasst_val.jsonl", self.oasst("validation"), "conversations")
        self.write("oasst_train.jsonl", self.oasst("train"), "conversations")
        self.write("dolly.jsonl", self.dolly(), "conversations")
        # Preserve publisher documentation locally along with source revisions.
        for source in SOURCES:
            self.download(source, "README.md")
        self.download("oasst", "LICENSE")
        manifest = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "collector_sha256": file_hash(__file__), "settings": {"story_mb": story_mb, "education_mb": education_mb, "max_chat_chars": self.max_chat_chars},
                    "sources": SOURCES, "assets": self.assets, "outputs": self.outputs,
                    "notes": ["No pretrained weights. TinyStories and Cosmopedia are synthetic and can contain factual errors.",
                              "Complete documents and conversation paths only; no blind paragraph splitting or answer truncation.",
                              "Official validation partitions retained. Other records use deterministic group splits in prepare.py.",
                              "Exact normalized deduplication only; not semantic deduplication or an independent factual audit."]}
        (self.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.client.close()
        print(json.dumps(self.outputs, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/expanded_sources")
    parser.add_argument("--story-mb", type=float, default=80)
    parser.add_argument("--education-mb", type=float, default=110)
    parser.add_argument("--max-chat-chars", type=int, default=3800)
    args = parser.parse_args()
    if not 1 <= args.story_mb <= 250 or not 1 <= args.education_mb <= 250 or not 256 <= args.max_chat_chars <= 20000:
        parser.error("Use 1-250 MB per corpus and 256-20000 chat characters.")
    Collector(args.out, args.max_chat_chars).run(args.story_mb, args.education_mb)


if __name__ == "__main__":
    main()
