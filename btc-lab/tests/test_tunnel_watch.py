import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        'tunnel_watch', ROOT / 'deploy' / 'tunnel_watch.py',
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watch = load()


class TunnelWatchTests(unittest.TestCase):
    def test_access_redirect_is_a_connected_tunnel_and_not_the_app(self):
        body = b'<html>302 Found cloudflare</html>'
        self.assertTrue(watch.edge_connected(302, body))
        action, streak, reason = watch.decide(1_000, True, True, 4, [])
        self.assertEqual((action, streak, reason), ('none', 0, 'tunnel_connected'))

    def test_error_1033_restarts_only_after_a_second_failure(self):
        body = b'Error 1033 Ray ID: abc Cloudflare Tunnel error'
        self.assertFalse(watch.edge_connected(530, body))
        action, streak, reason = watch.decide(1_000, True, False, 0, [])
        self.assertEqual((action, streak, reason), ('none', 1, 'failure_pending'))
        action, streak, reason = watch.decide(1_060, True, False, streak, [])
        self.assertEqual((action, streak, reason), ('restart', 0, 'tunnel_down'))

    def test_a_down_network_is_not_a_restart(self):
        action, streak, reason = watch.decide(1_000, False, False, 5, [])
        self.assertEqual((action, streak, reason), ('none', 0, 'network_down'))

    def test_restarts_are_rate_limited(self):
        attempts = [900, 940, 980]
        action, _streak, reason = watch.decide(1_000, True, False, 2, attempts)
        self.assertEqual(action, 'restart_limited')
        self.assertEqual(reason, 'rate_limit')
        action, _streak, reason = watch.decide(2_000, True, False, 2, [1_500])
        self.assertEqual(action, 'restart_limited')

    def test_the_restart_command_targets_the_existing_tunnel_only(self):
        self.assertEqual(watch.TUNNEL_LABEL, 'system/com.cloudflare.cloudflared')
        self.assertNotIn('paper', watch.TUNNEL_LABEL)
        self.assertNotIn('btc-lab.paper', watch.restart_tunnel.__code__.co_consts.__repr__())
