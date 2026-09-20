"""Bounded, revision-pinned story and educational text collection."""
import json
from pathlib import Path
from collect_data import Collector, SOURCES, file_hash


def main():
    directory = Path("data/base-sources")
    if (directory / "manifest.json").exists():
        raise ValueError("Corpus already collected; use the existing manifest.")
    collector = Collector(directory, 3800)
    try:
        collector.write("stories_val.jsonl", collector.stories("validation", 4_000_000), "documents")
        collector.write("stories_train.jsonl", collector.stories("train", 40_000_000), "documents")
        for subset in ("khanacademy", "openstax"):
            collector.write(f"education_{subset}.jsonl", collector.education(subset), "documents", 30_000_000)
        for source in ("tinystories", "cosmopedia"):
            collector.download(source, "README.md")
        manifest = {"sources": {k:SOURCES[k] for k in ("tinystories", "cosmopedia")},
                    "assets": collector.assets, "outputs": collector.outputs,
                    "collector_sha256": file_hash(__file__),
                    "note": "Synthetic text, not a fact-checked knowledge base. Complete records; exact deduplication. Bounded prefixes are not representative random samples."}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finally:
        collector.client.close()


if __name__ == "__main__":
    main()
