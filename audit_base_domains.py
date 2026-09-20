"""Compare the same held-out story/education tokens before and after pretraining."""
from contextlib import nullcontext
import json
from pathlib import Path
import sqlite3
import numpy as np
import torch
from backend import resolve_device
from config import ModelConfig
from data import Corpus
from model import LucidAI
from prepare import digest
from tokenizer import encode_text, load_tokenizer, fingerprint
from train import evaluate, load_checkpoint

ROOT = Path(__file__).resolve().parent


def main():
    torch.set_num_threads(4)
    output = ROOT / "runs/base-domain-audit"
    output.mkdir(exist_ok=False)
    tokenizer = load_tokenizer(ROOT / "data/base-expanded/tokenizer.json")
    with sqlite3.connect(ROOT / "data/base-expanded/records.sqlite") as db:
        heldout = {key for (key,) in db.execute("SELECT key FROM records WHERE kind='text' AND split='val'")}
    sources = {"stories": "stories_val.jsonl", "education_khanacademy": "education_khanacademy.jsonl",
               "education_openstax": "education_openstax.jsonl"}
    report = {"domains": {}, "before": {}, "after": {},
              "note": "Same deterministic 32 random windows per domain before/after; existing corpus split limitations apply. Not factual accuracy."}
    for domain, filename in sources.items():
        rows = [json.loads(line) for line in (ROOT / "data/base-sources" / filename).read_text(encoding="utf-8").splitlines()]
        rows = sorted((r for r in rows if digest(r["text"]) in heldout), key=lambda r:digest(r["text"]))[:300]
        binary = output / f"{domain}.bin"
        with binary.open("wb") as stream:
            for row in rows:
                ids = encode_text(tokenizer, row["text"]) + [tokenizer.token_to_id("<|eos|>")]
                np.asarray(ids, dtype="<u4").tofile(stream)
        report["domains"][domain] = {"documents": len(rows), "tokens": binary.stat().st_size // 4,
                                      "sha256": fingerprint(binary)}
    device = resolve_device("directml")
    for label, folder in (("before", "learning-pretrain"), ("after", "base-expanded")):
        saved = load_checkpoint(ROOT / "checkpoints" / folder / "best.pt")
        assert saved["tokenizer_sha256"] == fingerprint(ROOT / "data/base-expanded/tokenizer.json")
        model = LucidAI(ModelConfig(**saved["config"])).to(device)
        model.load_state_dict(saved["model"])
        for domain in sources:
            corpus = Corpus(output / f"{domain}.bin", model.config.context_length)
            value = evaluate(model, corpus, 1, 32, device, nullcontext)
            report[label][domain] = value
            print(f"{label} {domain}: {value:.4f}", flush=True)
        del model, saved
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Domain audit complete.", flush=True)


if __name__ == "__main__":
    main()
