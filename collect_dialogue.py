"""Collect publisher-reviewed English conversation paths with provenance."""
import json
from pathlib import Path
from collect_data import Collector, SOURCES


def main():
    out = Path("data/dialogue-sources")
    if (out / "manifest.json").exists():
        raise ValueError("Collection already exists; use its verified files.")
    collector = Collector(out, 12000)
    try:
        for split in ("validation", "train"):
            collector.write(f"oasst_{split}.jsonl", collector.oasst(split), "conversations")
        collector.download("oasst", "README.md")
        collector.download("oasst", "LICENSE")
        manifest = {"source": SOURCES["oasst"], "assets": collector.assets,
                    "outputs": collector.outputs,
                    "note": "Publisher review/rank and English filters; complete paths. Not individually fact-checked."}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finally:
        collector.client.close()


if __name__ == "__main__":
    main()
