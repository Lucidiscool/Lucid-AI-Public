"""Keep connected documents, duplicate records and conversation branches together."""
import hashlib


class SplitPlanner:
    def __init__(self, validation_fraction):
        self.fraction = validation_fraction
        self.parents = {}
        self.explicit = {}

    def root(self, key):
        self.parents.setdefault(key, key)
        parent = key
        while self.parents[parent] != parent:
            parent = self.parents[parent]
        while key != parent:
            previous = self.parents[key]
            self.parents[key] = parent
            key = previous
        return parent

    def add(self, key, links=(), split=None):
        if split not in (None, "train", "val"):
            raise ValueError("Explicit split must be 'train' or 'val'.")
        for link in links:
            left, right = sorted((self.root(key), self.root(link)))
            self.parents[right] = left
        self.root(key)
        if split is not None:
            self.explicit.setdefault(key, set()).add(split)

    def resolve(self):
        overrides = {}
        for key, splits in self.explicit.items():
            overrides.setdefault(self.root(key), set()).update(splits)
        result = {}
        for key in self.parents:
            root = self.root(key)
            requested = overrides.get(root, set())
            # Held-out copies win: never move an official validation example
            # into training, even when another file contains a duplicate.
            score = int(hashlib.sha256(root.encode()).hexdigest()[:8], 16) / 2**32
            result[key] = ("val" if "val" in requested else "train" if "train" in requested
                           else "val" if score < self.fraction else "train")
        return result
