import time
import unittest
from admin_service import AdminService


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.admin = AdminService('test-only-passphrase-123')

    def test_private_reads_and_writes_require_login(self):
        for action in ('dashboard', 'local', 'cloud', 'logout'):
            with self.assertRaises(PermissionError):
                self.admin.action('visitor-session-token', action)
        with self.assertRaises(ValueError):
            self.admin.login('incorrect')
        token = self.admin.login('test-only-passphrase-123')['token']
        self.assertEqual(self.admin.action(token, 'dashboard')['requests'], 0)
        self.admin.action(token, 'logout')
        with self.assertRaises(PermissionError):
            self.admin.action(token, 'dashboard')

    def test_four_digit_passcode_and_stricter_attempt_limit(self):
        service = AdminService('3553')
        token = service.login('3553')['token']
        self.assertEqual(service.action(token, 'dashboard')['requests'], 0)
        self.assertEqual(service.login_window, 3600)
        for _ in range(4):
            with self.assertRaises(ValueError): service.login('wrong')
        with self.assertRaisesRegex(ValueError, 'Too many'):
            service.login('3553')

    def test_expiry_rate_limit_and_disabled_by_default(self):
        with self.assertRaises(ValueError):
            AdminService('').login('anything')
        token = self.admin.login('test-only-passphrase-123')['token']
        self.admin.tokens[token] = time.monotonic() - 1
        with self.assertRaises(PermissionError): self.admin.action(token, 'dashboard')
        for _ in range(4):
            with self.assertRaises(ValueError): self.admin.login('bad')
        with self.assertRaisesRegex(ValueError, 'Too many'):
            self.admin.login('test-only-passphrase-123')

    def test_activity_bounds_counts_and_private_copy(self):
        for i in range(2005):
            self.admin.record('visitor-'+str(i % 2), '/good', [])
        token = self.admin.login('test-only-passphrase-123')['token']
        view = self.admin.action(token, 'dashboard')
        self.assertEqual(view['requests'], 2000)
        self.assertEqual(view['visitors'], 2)
        self.assertEqual(view['features'], {'/good': 2000})
        self.assertEqual(len(view['activity']), 200)
        view['activity'][0]['message'] = 'tampered'
        self.assertEqual(self.admin.action(token, 'dashboard')['activity'][0]['message'], '/good')
        for row in self.admin.activity: row['time'] = time.time() - 86401
        self.assertEqual(self.admin.action(token, 'dashboard')['requests'], 0)
        self.assertNotIn('activity', self.admin.config())

    def test_pc_is_the_only_host_and_cloud_switch_is_removed(self):
        token = self.admin.login('test-only-passphrase-123')['token']
        self.assertEqual(self.admin.config(), {'provider': 'local'})
        self.assertEqual(self.admin.action(token, 'dashboard')['hosting'], {'provider': 'local'})
        with self.assertRaises(ValueError): self.admin.action(token, 'cloud')


if __name__ == '__main__':
    unittest.main()
