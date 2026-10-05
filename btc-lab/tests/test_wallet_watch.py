import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from lab.core import Store
from lab.wallet_copy import WalletCopy, due_skip_reviews
from lab.wallet_observer import WALLETS
from lab.wallet_watch import build_watch


def review(reason, shadow_status, pnl=None, fee=1000, slug='btc-updown-5m-1', seen=1000):
    return json.dumps({
        'reason': reason,
        'status': 'RESOLVED' if shadow_status == 'SETTLED' else 'PENDING',
        'official_seen_at': seen,
        'source_event': {'slug': slug, 'side': 'BUY'},
        'shadow': {
            'status': shadow_status,
            'pnl_micro': pnl,
            'fill': {'fee': fee, 'cost': 500000, 'shares': 2000000},
        },
    })


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lab.db')
        self.now = 1_000_000.0
        self.engine = WalletCopy(self.store, lambda url: {}, clock=lambda: self.now)
        self.wallet = '0x' + 'ab' * 20
        with self.store.connect() as db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS wallet_activity '
                '(wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, '
                'PRIMARY KEY(wallet,event_key))'
            )

    def tearDown(self):
        self.temp.cleanup()

    def observe(self, status='POLL_OK', checked_at=None, error=None):
        self.store.set('wallet_roster', {'wallets': {
            self.wallet: {'wallet': self.wallet, 'state': 'observed', 'since': self.now - 2 * 86400},
        }})
        self.store.set('wallet_observer:' + self.wallet, {
            'status': status, 'checked_at': self.now if checked_at is None else checked_at, 'error': error,
        })

    def activity(self, key, source_ts, side='BUY'):
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (self.wallet, key, source_ts, source_ts, json.dumps({'side': side})),
            )

    def skip(self, key, body, end):
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                (self.wallet, key, end, 0, body),
            )

    def summary(self):
        return build_watch(self.store, self.now)[self.wallet]

    def test_settled_net_is_after_the_recorded_fee_and_open_stays_separate(self):
        self.observe()
        self.activity('buy', self.now - 10)
        self.skip('done', review('COPY_PAUSED', 'SETTLED', pnl=1_500_000, slug='btc-updown-5m-1'), 900)
        self.skip('open', review('COPY_PAUSED', 'FILLED_PENDING_SETTLEMENT', pnl=None, slug='btc-updown-5m-2'), 2_000)
        self.skip('late', review('COPY_BUY_TOO_LATE', 'SETTLED', pnl=-2_000_000, slug='btc-updown-5m-3'), 800)
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO wallet_copy_events VALUES (?,?,?,?,?)',
                (self.wallet, 'buy', self.now - 8, 'COPY_PAUSED', '{}'),
            )
        row = self.summary()
        self.assertEqual(row['intake'], 'receiving')
        self.assertEqual(row['last_reason'], 'COPY_PAUSED')
        self.assertEqual(row['hypothetical_open'], 1)
        self.assertEqual(row['hypothetical_settled'], 1)
        self.assertAlmostEqual(row['hypothetical_net_usd'], 1.5)
        self.assertEqual(len(row['journal']), 1)
        self.assertEqual(row['journal'][0]['pnl_micro'], 1_500_000)
        self.assertEqual(row['journal'][0]['cost_micro'], 500000)
        self.assertEqual(row['journal'][0]['side'], 'BUY')
        self.assertEqual(row['journal'][0]['closed_at'], 1000)
        self.assertTrue(row['hypothetical_fees_known'])
        self.assertEqual(row['other_hypothetical_settled'], 1)
        self.assertAlmostEqual(row['other_net_usd'], -2)
        self.assertFalse(row['policy_known'])
        self.assertIsNone(row['policy_net_usd'])
        self.assertIsNone(row['progress']['settled'])
        self.assertIsNone(row['progress']['windows'])
        self.assertIsNone(row['progress']['net_usd'])
        self.assertEqual(row['progress']['need_settled'], 20)
        self.assertAlmostEqual(row['progress']['observation_days'], 2, places=2)
        self.assertIsNotNone(row['last_buy_at'])

    def test_no_settlement_is_missing_net_not_zero(self):
        self.observe()
        self.activity('old', self.now - 10_000)
        row = self.summary()
        self.assertEqual(row['intake'], 'no_fresh_source_trades')
        self.assertEqual(row['activity_count'], 1)
        self.assertEqual(row['hypothetical_open'], 0)
        self.assertEqual(row['hypothetical_settled'], 0)
        self.assertIsNone(row['hypothetical_net_usd'])
        self.assertIsNone(row['progress']['evidence_days'])
        self.assertIsNone(row['progress']['net_usd'])

    def test_confirmed_empty_poll_is_no_source_trades(self):
        self.observe()
        row = self.summary()
        self.assertEqual(row['feed'], 'ok')
        self.assertEqual(row['intake'], 'no_source_trades')
        self.assertEqual(row['activity_count'], 0)
        self.assertIsNone(row['hypothetical_net_usd'])

    def test_feed_error_is_not_reported_as_no_trades(self):
        self.observe(status='ERROR', error='HTTP 403')
        row = self.summary()
        self.assertEqual(row['feed'], 'down')
        self.assertEqual(row['intake'], 'feed_down')
        self.assertNotEqual(row['intake'], 'no_source_trades')
        self.assertIsNone(row['hypothetical_net_usd'])

    def test_stale_check_is_a_feed_failure(self):
        self.observe(checked_at=self.now - 1000)
        self.activity('buy', self.now - 5)
        row = self.summary()
        self.assertEqual(row['intake'], 'feed_down')

    def test_missing_fee_does_not_claim_a_net_after_costs(self):
        self.observe()
        self.activity('buy', self.now - 5)
        self.skip('done', review('COPY_PAUSED', 'SETTLED', pnl=1_500_000, fee=None), 900)
        row = self.summary()
        self.assertEqual(row['hypothetical_settled'], 1)
        self.assertIsNone(row['hypothetical_net_usd'])
        self.assertFalse(row['hypothetical_fees_known'])

    def test_publish_uses_the_cached_watch_and_keeps_paper_pnl_separate(self):
        wallet = WALLETS[0]
        self.store.set('wallet_roster', {'wallets': {
            wallet: {'wallet': wallet, 'state': 'observed', 'since': self.now},
        }})
        self.engine.watch = {wallet: {
            'hypothetical_open': 3, 'hypothetical_settled': 0, 'hypothetical_net_usd': None, 'shadow_known': True,
        }}
        self.engine.publish('TEST')
        account = next(item for item in self.engine.store.get('wallet_copy_execution')['accounts'] if item['wallet'] == wallet)
        self.assertEqual(account['roster_state'], 'observed')
        self.assertEqual(account['watch']['hypothetical_open'], 3)
        self.assertIsNone(account['watch']['hypothetical_net_usd'])
        self.assertEqual(account['pnl'], 0)
        self.assertEqual(account['trades'], 0)

    def test_ended_hypothetical_fill_is_reviewed_before_an_older_skip(self):
        other = '0x' + 'cd' * 20
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                (other, 'old', 100, 0, review('SOURCE_TOO_OLD', 'UNAVAILABLE', pnl=None)),
            )
            db.execute(
                'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                (self.wallet, 'fill', 500, 0, review('COPY_PAUSED', 'FILLED_PENDING_SETTLEMENT', pnl=None)),
            )
            chosen = due_skip_reviews(db, 1000)
            positions = db.execute('SELECT COUNT(*) FROM wallet_copy_positions').fetchone()[0]
        self.assertEqual(chosen[0]['event_key'], 'fill')
        self.assertEqual(positions, 0)
        self.assertNotIn('old', [row['event_key'] for row in chosen[:1]])

    def test_eight_unresolved_markets_do_not_block_the_ninth(self):
        now = 50_000.0
        self.engine.clock = lambda: now
        fetched = []

        def fetch(url):
            cid = url.rstrip('/').rsplit('/', 1)[-1]
            fetched.append(cid)
            if cid == 'ninth':
                return {
                    'condition_id': 'ninth', 'closed': True,
                    'tokens': [{'token_id': '1', 'winner': True}, {'token_id': '2', 'winner': False}],
                }
            return {
                'condition_id': cid, 'closed': False,
                'tokens': [{'token_id': '1', 'winner': False}, {'token_id': '2', 'winner': False}],
            }

        self.engine.fetch = fetch
        shares, cost, fee = 2_000_000, 500_000, 1_000

        def pending(condition, reason):
            return json.dumps({
                'reason': reason,
                'status': 'PENDING',
                'source_event': {'conditionId': condition, 'asset': '1', 'slug': 'btc-updown-5m-1'},
                'shadow': {
                    'status': 'FILLED_PENDING_SETTLEMENT',
                    'pnl_micro': None,
                    'fill': {'fee': fee, 'cost': cost, 'shares': shares},
                },
            })

        with self.store.connect() as db:
            for i in range(5):
                db.execute(
                    'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                    (self.wallet, f'noise{i}', 100 + i, 0, review('SOURCE_TOO_OLD', 'UNAVAILABLE', pnl=None)),
                )
            for i in range(8):
                db.execute(
                    'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                    (self.wallet, f'head{i}', 1_000 + i, now, pending(f'c{i}', 'COPY_POSITION_ALREADY_OPEN')),
                )
            db.execute(
                'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                (self.wallet, 'ninth', 2_000, 0, pending('ninth', 'COPY_PAUSED')),
            )
            before = db.execute('SELECT COUNT(*) FROM wallet_copy_positions').fetchone()[0]
        asyncio.run(self.engine.review_skips())
        with self.store.connect() as db:
            ninth = json.loads(db.execute(
                'SELECT body FROM wallet_copy_skip_reviews WHERE event_key=?', ('ninth',)
            ).fetchone()[0])
            heads = [
                json.loads(db.execute(
                    'SELECT body FROM wallet_copy_skip_reviews WHERE event_key=?', (f'head{i}',)
                ).fetchone()[0])
                for i in range(8)
            ]
            after = db.execute('SELECT COUNT(*) FROM wallet_copy_positions').fetchone()[0]
        self.assertEqual(ninth['status'], 'RESOLVED')
        self.assertEqual(ninth['shadow']['status'], 'SETTLED')
        self.assertEqual(ninth['shadow']['pnl_micro'], shares - cost - fee)
        self.assertTrue(all(row['shadow']['status'] == 'FILLED_PENDING_SETTLEMENT' for row in heads))
        self.assertNotIn('c0', fetched)
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
