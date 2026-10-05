import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_roster import (
    RULES, can_observe_to_test, evaluate_copy_book, tick, bootstrap, SPEC,
    hypothetical_settled, audit, AUDIT_TABLE, AUDIT_DISPLAY_LIMIT,
)

class RosterTests(unittest.TestCase):
    def test_rules_reenable_harder_than_pause(self):
        self.assertLess(RULES['paper_active_to_paused']['rolling_7d_net_usd'], 0)
        self.assertGreater(RULES['paused_to_paper_test']['hyp_7d_net_usd'], 0)
        self.assertGreaterEqual(
            RULES['paused_to_paper_test']['min_pause_days'], 14)

    def test_leaderboard_alone_does_not_qualify(self):
        self.assertFalse(can_observe_to_test({
            'our_trades': 40, 'windows': 10, 'age_days': 30,
            'copy_sim_net_usd': None, 'best_day_share': 0.2,
        }))
        self.assertTrue(can_observe_to_test({
            'our_trades': 40, 'windows': 10, 'age_days': 30,
            'copy_sim_net_usd': 12, 'best_day_share': 0.2,
        }))

    def test_one_lucky_day_blocks_activation(self):
        now=1_000_000
        closed=[{'status':'CLOSED','closed_at':now-86400,'pnl_micro':20_000_000,'market':'a'}]
        closed+=[{'status':'CLOSED','closed_at':now-2*86400,'pnl_micro':100_000,'market':f'm{i}'} for i in range(29)]
        book=evaluate_copy_book(closed,now,now-20*86400)
        self.assertFalse(book['can_activate'])

    def test_pause_and_retest_are_not_the_same_threshold(self):
        now=2_000_000
        losses=[{'status':'CLOSED','closed_at':now-i,'pnl_micro':-2_000_000,'market':str(i)} for i in range(8)]
        book=evaluate_copy_book(losses,now,now-20*86400)
        self.assertTrue(book['should_pause'])
        self.assertFalse(book['can_retest'])

    def test_bootstrap_keeps_seed_states_and_is_versioned(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'lab.db')
            state=bootstrap(store, now=10)
            self.assertEqual(state['spec'], SPEC)
            self.assertEqual(state['wallets']['0x16217458b59b3458149918058754cd234096b159']['state'],'paper_active')
            self.assertEqual(state['wallets']['0xeebde7a0e019a63e6b476eb425505b7b3e6eba30']['state'],'paused')
            again=bootstrap(store, now=20)
            self.assertEqual(again['wallets']['0x16217458b59b3458149918058754cd234096b159']['since'],10)

    def test_new_candidate_needs_copy_sim_not_public_month(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'lab.db')
            bootstrap(store, now=10)
            state,changed=tick(store, now=11, candidate_stats={
                '0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa': {
                    'our_trades':50,'windows':20,'age_days':30,
                    'copy_sim_net_usd':None,'best_day_share':0.1,
                }})
            self.assertEqual(changed,[])
            self.assertNotIn('0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', state['wallets'])

    def test_losing_paper_test_is_paused(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 3_000_000
            bootstrap(store, now=now)
            w = '0x84389cfc4a652ea14d8d8be969769b1f69de3680'
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE IF NOT EXISTS wallet_copy_positions '
                    '(id INTEGER PRIMARY KEY, body TEXT)'
                )
                for i in range(8):
                    db.execute(
                        'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                        (json.dumps({
                            'wallet': w,
                            'status': 'CLOSED',
                            'closed_at': now - i,
                            'opened': now - 86400,
                            'pnl_micro': -2_000_000,
                            'market': str(i),
                        }),),
                    )
            state, changed = tick(store, now=now)
            self.assertIn(w, changed)
            self.assertEqual(state['wallets'][w]['state'], 'paused')
            paused = [row for row in store.get('wallet_selection_audit') if row['wallet'] == w]
            self.assertEqual(paused[0]['action'], 'paused')
            self.assertEqual(paused[0]['reason'], 'paper-roster-v1 pause')

    def test_retest_uses_versioned_observation_not_independent_tickets(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 5_000_000
            state = bootstrap(store, now=now - 20 * 86400)
            w = '0xeebde7a0e019a63e6b476eb425505b7b3e6eba30'
            state['wallets'][w]['since'] = now - 20 * 86400
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_copy_skip_reviews '
                    '(wallet TEXT, event_key TEXT, end REAL, checked REAL, body TEXT, '
                    'PRIMARY KEY(wallet, event_key))'
                )
                for i in range(10):
                    db.execute(
                        'INSERT INTO wallet_copy_skip_reviews VALUES (?,?,?,?,?)',
                        (w, str(i), now, now, json.dumps({
                            'reason': 'COPY_PAUSED',
                            'official_seen_at': now - 86400,
                            'source_event': {'slug': f'm{i}'},
                            'shadow': {'status': 'SETTLED', 'pnl_micro': 1_000_000},
                        })),
                    )
            self.assertEqual(len(hypothetical_settled(store)[w]), 10)
            stayed, changed = tick(store, now=now)
            self.assertEqual(changed, [])
            self.assertEqual(stayed['wallets'][w]['state'], 'paused')
            store.set('wallet_observation_meta', {'version': 'copy-observe-v1', 'started_at': now - 30 * 86400})
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_observation_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)'
                )
                for i in range(10):
                    db.execute(
                        'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                        (str(i), w, json.dumps({
                            'policy': 'copy-observe-v1', 'status': 'CLOSED', 'opened': now - 20 * 86400,
                            'closed_at': now - 86400, 'pnl_micro': 1_000_000, 'market': f'obs{i}', 'fee': 1000,
                        })),
                    )
            updated, changed = tick(store, now=now)
            self.assertIn(w, changed)
            self.assertEqual(updated['wallets'][w]['state'], 'paper_test')
            restored = [row for row in store.get('wallet_selection_audit', []) if row['action'] == 'restored']
            self.assertEqual(restored[0]['reason'], 'paper-roster-v1 retest')
            self.assertEqual(restored[0]['wallet'], w)

    def test_observed_wallet_promotes_to_paper_test_not_active(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 8_000_000
            state = bootstrap(store, now=now)
            wallet = '0x' + 'ab' * 20
            state['wallets'][wallet] = {'wallet': wallet, 'state': 'observed', 'since': now - 10}
            store.set('wallet_roster', state)
            updated, changed = tick(store, now=now, candidate_stats={wallet: {
                'our_trades': 40, 'windows': 10, 'age_days': 30,
                'copy_sim_net_usd': 12, 'best_day_share': 0.2,
            }})
            self.assertEqual(updated['wallets'][wallet]['state'], 'paper_test')
            self.assertIn(wallet, changed)
            promoted = [row for row in store.get('wallet_selection_audit') if row['wallet'] == wallet]
            self.assertEqual([row['action'] for row in promoted], ['promoted'])
            self.assertEqual(promoted[0]['reason'], 'paper-roster-v1 paper_test')

    def test_first_sight_stays_observed_even_with_copy_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            wallet = '0x' + 'cd' * 20
            state, _changed = tick(store, now=100, candidate_stats={wallet: {
                'our_trades': 40, 'windows': 10, 'age_days': 30,
                'copy_sim_net_usd': 12, 'best_day_share': 0.2,
            }})
            self.assertEqual(state['wallets'][wallet]['state'], 'observed')

    def test_stronger_candidate_replaces_weakest_paper_test_without_deleting_losses(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 9_000_000
            state = bootstrap(store, now=now)
            weak = '0x' + 'bb' * 20
            newbie = '0x' + 'cd' * 20
            state['wallets'][weak] = {'wallet': weak, 'state': 'paper_test', 'since': now - 5}
            state['wallets'][newbie] = {'wallet': newbie, 'state': 'observed', 'since': now - 5}
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                db.execute(
                    'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                    (json.dumps({
                        'wallet': weak, 'status': 'CLOSED', 'closed_at': now - 10,
                        'opened': now - 20, 'pnl_micro': -500_000, 'market': 'kept',
                    }),),
                )
            updated, _changed = tick(store, now=now, candidate_stats={newbie: {
                'our_trades': 40, 'windows': 10, 'age_days': 30,
                'copy_sim_net_usd': 12, 'best_day_share': 0.2,
            }})
            self.assertEqual(updated['wallets'][newbie]['state'], 'paper_test')
            self.assertEqual(updated['wallets'][weak]['state'], 'observed')
            with store.connect() as db:
                kept = db.execute('SELECT body FROM wallet_copy_positions').fetchone()[0]
            self.assertEqual(json.loads(kept)['pnl_micro'], -500_000)
            actions = {row['wallet']: row for row in store.get('wallet_selection_audit')}
            self.assertEqual(actions[weak]['action'], 'replaced')
            self.assertEqual(actions[weak]['reason'], 'discovery-v1 replaced by stronger paper candidate')
            self.assertEqual(actions[newbie]['action'], 'promoted')
            self.assertEqual(actions[newbie]['reason'], 'paper-roster-v1 paper_test')

    def test_audit_table_keeps_history_and_display_stops_at_200(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            kept = '0x' + '11' * 20
            store.set('wallet_selection_audit', [{
                'ts': 1, 'wallet': kept, 'action': 'discovered',
                'reason': 'kept-from-before', 'evidence': {'note': 'existing'},
            }])
            audit(store, 2, '0x' + '22' * 20, 'rejected', 'wrong_markets', {})
            with store.connect() as db:
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {AUDIT_TABLE}').fetchone()[0], 2)
                self.assertEqual(
                    db.execute(
                        f"SELECT COUNT(*) FROM {AUDIT_TABLE} WHERE reason='kept-from-before'"
                    ).fetchone()[0],
                    1,
                )
            for i in range(AUDIT_DISPLAY_LIMIT + 5):
                audit(store, 10 + i, '0x' + '33' * 20, 'rejected', f'row-{i}', {})
            self.assertEqual(len(store.get('wallet_selection_audit')), AUDIT_DISPLAY_LIMIT)
            with store.connect() as db:
                self.assertEqual(
                    db.execute(f'SELECT COUNT(*) FROM {AUDIT_TABLE}').fetchone()[0],
                    2 + AUDIT_DISPLAY_LIMIT + 5,
                )
                self.assertEqual(
                    db.execute(
                        f"SELECT evidence FROM {AUDIT_TABLE} WHERE reason='kept-from-before'"
                    ).fetchone()[0],
                    '{"note": "existing"}',
                )
