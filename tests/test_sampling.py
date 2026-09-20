import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch
from data import Conversations


class SamplingTests(unittest.TestCase):
    def test_weighted_distribution_and_rng_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "chat.jsonl"
            path.write_text("\n".join(json.dumps({"ids": [i, 2, 3], "labels": [-100, 2, 3],
                "sampling_weight": w}) for i, w in [(5, 1.0), (6, 9.0)]))
            data = Conversations(path, 8, 0)
            rng = np.random.default_rng(17)
            ids, _ = data.batch(4000, rng, "cpu")
            self.assertTrue(.87 < float((ids[:, 0] == 6).float().mean()) < .93)
            saved = copy.deepcopy(rng.bit_generator.state)
            expected = data.batch(16, rng, "cpu")
            restored = np.random.default_rng()
            restored.bit_generator.state = saved
            actual = data.batch(16, restored, "cpu")
            for left, right in zip(expected, actual):
                torch.testing.assert_close(left, right, atol=0, rtol=0)

    def test_rejects_invalid_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "chat.jsonl"
            for weight in (0, -1, float("nan"), float("inf")):
                path.write_text(json.dumps({"ids": [1, 2], "labels": [-100, 2], "sampling_weight": weight}))
                with self.assertRaises(ValueError):
                    Conversations(path, 8, 0)
