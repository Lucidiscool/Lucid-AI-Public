import unittest
import torch
from optim import DirectMLAdamW
from backend import cpu_tree


class OptimizerTests(unittest.TestCase):
    def test_portable_snapshot_does_not_share_cpu_state(self):
        original = {"step": torch.tensor(1.0), "nested": [torch.tensor([2.0])]}
        snapshot = cpu_tree(original)
        original["step"].add_(1)
        original["nested"][0].add_(3)
        self.assertEqual(snapshot["step"].item(), 1.0)
        self.assertEqual(snapshot["nested"][0].item(), 2.0)

    def test_matches_torch_adamw_and_resumes(self):
        torch.manual_seed(3)
        a = torch.nn.Parameter(torch.randn(7, 9))
        b = torch.nn.Parameter(a.detach().clone())
        reference = torch.optim.AdamW([a], lr=0.002, betas=(0.9, 0.95), weight_decay=0.1, foreach=False)
        actual = DirectMLAdamW([b], lr=0.002, betas=(0.9, 0.95), weight_decay=0.1)
        for index in range(8):
            gradient = torch.randn_like(a)
            a.grad, b.grad = gradient.clone(), gradient.clone()
            reference.step()
            actual.step()
            torch.testing.assert_close(a, b, atol=1e-6, rtol=1e-6)
            if index == 3:
                restored = DirectMLAdamW([b])
                restored.load_state_dict(actual.state_dict())
                actual = restored
