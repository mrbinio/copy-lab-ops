import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ['BTC_LAB_LABEL'] = 'gui/1/com.btc-lab.isolated-test'
os.environ['BTC_LAB_PORT'] = '8774'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'deploy' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watchdog = load('service_watchdog')
service = load('macos_service')


class WatchdogSplitTests(unittest.TestCase):
    def test_a_late_publish_restarts_even_when_the_heartbeat_is_fresh(self):
        now = 1_000_000
        state = {
            'worker': {'heartbeat': now - 10},
            'wallet_copy_execution': {'updated_at': now - 400},
            'mitch_copy': {'updated_at': now - 10},
            'wallet_copy_progress': {'at': now - 5, 'queue': 0},
            'mitch_progress': {'at': now - 5, 'queue': 0},
        }
        restart, noted, _ages = watchdog.assess(now, state, False, process_age=1000)
        self.assertIn('copy_publish', restart)
        self.assertNotIn('heartbeat', restart)
        self.assertIn('connection', noted)
        self.assertNotIn('connection', restart)

    def test_a_ledger_hold_is_not_a_restart(self):
        now = 1_000_000
        state = {
            'worker': {'heartbeat': now - 5},
            'wallet_copy_health': {'status': 'ledger_mismatch'},
        }
        restart, noted, _ages = watchdog.assess(now, state, True)
        self.assertEqual(restart, [])
        self.assertEqual(noted, ['ledger_mismatch'])

    def test_a_starting_process_is_not_restarted_during_the_open(self):
        now = 1_000_000
        state = {'worker': {'heartbeat': now - 200, 'status': 'STARTING'}}
        restart, noted, _ages = watchdog.assess(now, state, False, process_age=200)
        self.assertEqual(restart, [])
        self.assertIn('starting', noted)

    def test_only_a_stale_heartbeat_is_a_restart(self):
        now = 1_000_000
        state = {'worker': {'heartbeat': now - 200}}
        restart, noted, _ages = watchdog.assess(now, state, True)
        self.assertEqual(restart, ['heartbeat'])
        self.assertEqual(noted, [])

    def test_a_growing_queue_is_noted_and_not_restarted(self):
        now = 1_000_000
        state = {
            'worker': {'heartbeat': now - 5, 'status': 'RECORDING'},
            'wallet_copy_execution': {'updated_at': now - 5},
            'mitch_copy': {'updated_at': now - 5},
            'wallet_copy_progress': {'at': now - 2, 'backlog': 3},
            'mitch_progress': {
                'at': now - 2, 'backlog': 40, 'book_pool_ms': 2500,
                'expired_recent': 5, 'arrivals_60s': 4, 'decisions_60s': 0,
                'oldest_fresh_age_s': 30,
            },
        }
        previous = {'ages': {'mitch_backlog': 10}}
        restart, noted, ages = watchdog.assess(
            now, state, True, process_age=1000, previous=previous,
        )
        self.assertEqual(restart, [])
        self.assertIn('mitch_backlog_growing', noted)
        self.assertIn('book_wait', noted)
        self.assertIn('signals_expired_by_us', noted)
        self.assertIn('mitch_no_useful_progress', noted)
        self.assertEqual(ages['mitch_backlog'], 40)

    def test_a_recent_wake_does_not_restart_a_frozen_heartbeat(self):
        now = 1_000_000
        state = {'worker': {'heartbeat': now - 900, 'status': 'RECORDING'}}
        restart, noted, _ages = watchdog.assess(
            now, state, True, process_age=5000, wake_age=12,
        )
        self.assertEqual(restart, [])
        self.assertIn('recent_wake', noted)

    def test_a_launch_wait_suppresses_the_restart(self):
        now = 1_000_000
        state = {'worker': {'heartbeat': now - 500}}
        restart, noted, _ages = watchdog.assess(
            now, state, False, {'status': 'waiting', 'retry_at': now + 30},
        )
        self.assertEqual(restart, [])
        self.assertIn('launch_wait', noted)

    def test_five_launches_wait_and_then_start(self):
        now = 5_000
        attempts = [now - 100, now - 80, now - 60, now - 40, now - 20]
        self.assertEqual(service.launch_decision(attempts, now)[0], 'wait')
        later = now + 600
        decision, fresh = service.launch_decision(attempts, later)
        self.assertEqual(decision, 'start')
        self.assertEqual(fresh, [])


class IsolatedWatchdogTests(unittest.TestCase):
    def test_isolated_root_reports_publish_and_connection_without_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'logs').mkdir()
            db = sqlite3.connect(root / 'data' / 'lab.sqlite')
            db.execute('CREATE TABLE state (key TEXT PRIMARY KEY, body TEXT)')
            now = 2_000_000
            rows = {
                'worker': {'heartbeat': now - 5, 'status': 'RECORDING'},
                'wallet_copy_execution': {'updated_at': now - 400},
                'mitch_copy': {'updated_at': now - 5},
                'wallet_copy_health': {'status': 'ok'},
            }
            for key, body in rows.items():
                db.execute('INSERT INTO state VALUES (?,?)', (key, json.dumps(body)))
            db.commit()
            db.close()
            watchdog.ROOT = root
            watchdog.ATTEMPTS = root / 'watchdog-attempts.json'
            watchdog.STATUS = root / 'logs' / 'watchdog-status.json'
            watchdog.PORT = 8774
            watchdog.process_age = lambda _now: 1000

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(500)
                    self.end_headers()
                def log_message(self, *_args):
                    return

            server = ThreadingHTTPServer(('127.0.0.1', 8774), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                saved = watchdog.time.time
                watchdog.time.time = lambda: now
                try:
                    watchdog.main()
                finally:
                    watchdog.time.time = saved
            finally:
                server.shutdown()
            status = json.loads((root / 'logs' / 'watchdog-status.json').read_text())
            self.assertEqual(status['action'], 'restart_requested')
            self.assertIn('copy_publish', status['problems'])
            self.assertIn('connection', status['noted'])
            self.assertTrue((root / 'watchdog-attempts.json').exists())
            proof = json.loads((root / 'logs' / 'watchdog-restart.json').read_text())
            self.assertFalse(proof['verified'])
