import unittest
from splits import SplitPlanner


class SplitTests(unittest.TestCase):
    def test_duplicate_bridges_and_official_validation(self):
        rows = [("a", ["group:one"], "train"), ("b", ["group:two"], None),
                ("a", ["group:two"], "val"), ("c", ["group:three"], "train")]
        outcomes = []
        for entries in (rows, list(reversed(rows))):
            planner = SplitPlanner(0.05)
            for key, links, split in entries:
                planner.add(key, links, split)
            result = planner.resolve()
            self.assertEqual(result["a"], "val")
            self.assertEqual(result["b"], "val")
            self.assertEqual(result["c"], "train")
            outcomes.append(result)
        self.assertEqual(outcomes[0], outcomes[1])

    def test_shared_prompt_connects_different_groups(self):
        planner = SplitPlanner(0.05)
        planner.add("first", ["group:a", "prompt:hello"], "val")
        planner.add("second", ["group:b", "prompt:hello"])
        planner.add("third", ["group:b"])
        self.assertEqual(planner.resolve()["third"], "val")
        with self.assertRaises(ValueError):
            planner.add("bad", split="test")
