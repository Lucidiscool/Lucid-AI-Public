import json
from pathlib import Path
import numpy as np
import torch


class Corpus:
    def __init__(self, path, context):
        self.tokens = np.memmap(path, dtype="<u4", mode="r")
        self.context = context
        if len(self.tokens) < context + 1:
            raise ValueError(f"{path}: need at least {context + 1} tokens.")

    def batch(self, size, rng, device):
        starts = rng.integers(0, len(self.tokens) - self.context, size=size)
        rows = np.stack([self.tokens[i:i + self.context + 1] for i in starts]).astype(np.int64)
        batch = torch.from_numpy(rows).to(device)
        return batch[:, :-1], batch[:, 1:]


class Conversations:
    def __init__(self, path, context, pad_id):
        self.rows, self.context, self.pad_id = [], context, pad_id
        self.skipped = 0
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                # Never silently cut an answer in half or discard its end token.
                if len(row["ids"]) > context + 1:
                    self.skipped += 1
                    continue
                if len(row["ids"]) != len(row["labels"]) or not any(x != -100 for x in row["labels"][1:]):
                    raise ValueError(f"Invalid conversation in {path}")
                self.rows.append(row)
        if not self.rows:
            raise ValueError(f"No conversations fit context={context} in {path}.")
        weights = np.asarray([row.get("sampling_weight", 1.0) for row in self.rows], dtype=np.float64)
        if not np.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError("Conversation sampling weights must be positive and finite.")
        # Preserve the original random stream for unweighted datasets/resumes.
        self.probabilities = None if np.all(weights == weights[0]) else weights / weights.max()
        if self.probabilities is not None:
            self.probabilities /= self.probabilities.sum()
        print(f"{path}: {len(self.rows):,} conversations; {self.skipped:,} too long and skipped.")

    def batch(self, size, rng, device):
        indices = (rng.integers(0, len(self.rows), size=size) if self.probabilities is None else
                   rng.choice(len(self.rows), size=size, p=self.probabilities))
        rows = [self.rows[i] for i in indices]
        length = max(len(row["ids"]) for row in rows)
        ids = torch.full((size, length), self.pad_id, dtype=torch.long)
        labels = torch.full_like(ids, -100)
        for index, row in enumerate(rows):
            ids[index, :len(row["ids"])] = torch.tensor(row["ids"])
            labels[index, :len(row["labels"])] = torch.tensor(row["labels"])
        return ids[:, :-1].to(device), labels[:, 1:].to(device)


def load_data(directory, stage, context, pad_id):
    directory = Path(directory)
    if stage == "pretrain":
        return tuple(Corpus(directory / f"pretrain_{split}.bin", context) for split in ("train", "val"))
    return tuple(Conversations(directory / f"chat_{split}.jsonl", context, pad_id) for split in ("train", "val"))
