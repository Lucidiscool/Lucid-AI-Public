import unittest
from unittest.mock import Mock, patch
from train import replace_with_retry


class FileRetryTests(unittest.TestCase):
    @patch("train.time.sleep")
    def test_temporary_lock_recovers(self, sleep):
        temporary = Mock()
        temporary.replace.side_effect = [PermissionError("locked"), PermissionError("locked"), None]
        replace_with_retry(temporary, "target")
        self.assertEqual(temporary.replace.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("train.time.sleep")
    def test_persistent_checkpoint_lock_is_not_silenced(self, sleep):
        temporary = Mock()
        temporary.replace.side_effect = PermissionError("locked")
        with self.assertRaises(PermissionError):
            replace_with_retry(temporary, "target")
        self.assertEqual(temporary.replace.call_count, 6)
