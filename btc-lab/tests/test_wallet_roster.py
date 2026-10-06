import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_roster import (
    RULES, RULES_V1, RULES_V2, can_observe_to_test, copy_evidence, evaluate_copy_book, tick, bootstrap, SPEC,
    SPEC_V2, PREVIOUS_SPEC, hypothetical_settled, audit, AUDIT_TABLE, AUDIT_DISPLAY_LIMIT,
    PAUSE_REASON, RETEST_REASON, RESTORE_PLUS_REASON, PROMOTE_REASON,
    pause_if_period_negative, buy_pause_reason,
)

class RosterTests(unittest.TestCase):
    def test_rules_reenable_harder_than_pause(self):
        self.assertEqual(RULES['observed_to_paper_test']['min_days'], 0)
        self.assertEqual(RULES['paper_test_to_paper_active']['min_days'], 0)
        self.assertEqual(RULES['paused_to_paper_test']['min_pause_days'], 0)
        self.assertNotIn('hyp_7d_net_usd', RULES['paused_to_paper_test'])
        self.assertNotIn('min_hyp_trades', RULES['paused_to_paper_test'])
        self.assertTrue(RULES['paper_active_to_paused']['period_net_negative_blocks_buys'])
        self.assertNotIn('max_best_day_share', RULES['observed_to_paper_test'])
        self.assertNotIn('max_best_day_share', RULES['paper_test_to_paper_active'])
        self.assertEqual(RULES['concentration_uncertain_above'], 0.70)
        self.assertEqual(RULES_V2['observed_to_paper_test']['max_best_day_share'], 0.70)
        self.assertEqual(RULES_V2['paper_test_to_paper_active']['max_best_day_share'], 0.70)
        self.assertEqual(RULES_V1['spec'], PREVIOUS_SPEC)
        self.assertEqual(RULES_V1['observed_to_paper_test']['min_days'], 7)
        self.assertEqual(RULES_V1['paper_active_to_paused']['rolling_7d_net_usd'], -15.0)
        self.assertEqual(RULES_V1['paused_to_paper_test']['hyp_7d_net_usd'], 8.0)
        self.assertTrue(can_observe_to_test({
            'our_trades': 20, 'windows': 5, 'age_days': 0,
            'copy_sim_net_usd': 1, 'best_day_share': 1,
        }))

    def test_leaderboard_alone_does_not_qualify(self):
        self.assertFalse(can_observe_to_test({
            'our_trades': 40, 'windows': 10, 'age_days': 30,
            'copy_sim_net_usd': None, 'best_day_share': 0.2,
        }))
        self.assertTrue(can_observe_to_test({
            'our_trades': 40, 'windows': 10, 'age_days': 0,
            'copy_sim_net_usd': 12, 'best_day_share': 0.2,
        }))

    def test_one_day_concentration_does_not_block(self):
        now=1_000_000
        closed=[{'status':'CLOSED','opened':now-3600,'closed_at':now-3600,'pnl_micro':1_000_000,'market':f'm{i}'} for i in range(30)]
        book=evaluate_copy_book(closed,now,now-86400)
        self.assertEqual(book['best_day_share'], 1)
        self.assertTrue(book['concentration_uncertain'])
        self.assertTrue(book['can_activate'])

    def test_pause_and_retest_are_not_the_same_threshold(self):
        now=2_000_000
        losses=[{'status':'CLOSED','closed_at':now-i,'pnl_micro':-2_000_000,'market':str(i)} for i in range(8)]
        book=evaluate_copy_book(losses,now,now-20*86400)
        self.assertTrue(book['should_pause'])
        self.assertFalse(book['can_retest'])
        one=[{'status':'CLOSED','closed_at':now-1,'opened':now-2,'pnl_micro':-1,'market':'only'}]
        self.assertTrue(evaluate_copy_book(one,now,now-2)['should_pause'])
        unknown=[{'status':'CLOSED','closed_at':now-1,'opened':now-2,'pnl_micro':None,'market':'x'}]
        self.assertFalse(evaluate_copy_book(unknown,now,now-2)['should_pause'])
        self.assertIsNone(evaluate_copy_book(unknown,now,now-2)['net_usd'])

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
            state = store.get('wallet_roster')
            state['wallets'][w]['since'] = now - 86400
            store.set('wallet_roster', state)
            state, changed = tick(store, now=now)
            self.assertIn(w, changed)
            self.assertEqual(state['wallets'][w]['state'], 'paused')
            paused = [row for row in store.get('wallet_selection_audit') if row['wallet'] == w]
            self.assertEqual(paused[0]['action'], 'paused')
            self.assertEqual(paused[0]['reason'], PAUSE_REASON)

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
                            'policy': 'copy-observe-v1', 'status': 'CLOSED', 'opened': now - 21 * 86400,
                            'closed_at': now - 20 * 86400, 'pnl_micro': 2_000_000, 'market': f'old{i}', 'fee': 1000,
                        })),
                    )
            held, changed = tick(store, now=now)
            self.assertEqual(changed, [])
            self.assertEqual(held['wallets'][w]['state'], 'paused')
            with store.connect() as db:
                db.execute(
                    'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                    ('after', w, json.dumps({
                        'policy': 'copy-observe-v1', 'status': 'CLOSED', 'opened': now - 86400,
                        'closed_at': now - 3600, 'pnl_micro': 50_000, 'market': 'new', 'fee': 1000,
                    })),
                )
            updated, changed = tick(store, now=now)
            self.assertIn(w, changed)
            self.assertEqual(updated['wallets'][w]['state'], 'paper_test')
            self.assertEqual(updated['wallets'][w]['sample'], 'uncertain')
            restored = [row for row in store.get('wallet_selection_audit', []) if row['action'] == 'restored']
            self.assertEqual(restored[0]['reason'], RETEST_REASON)
            self.assertEqual(restored[0]['wallet'], w)
            self.assertEqual(restored[0]['evidence']['sample'], 'uncertain')

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
            self.assertEqual(promoted[0]['reason'], PROMOTE_REASON)

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
                        'wallet': weak, 'status': 'CLOSED', 'closed_at': now - 1,
                        'opened': now - 4, 'pnl_micro': -500_000, 'market': 'kept',
                    }),),
                )
            updated, _changed = tick(store, now=now, candidate_stats={newbie: {
                'our_trades': 40, 'windows': 10, 'age_days': 30,
                'copy_sim_net_usd': 12, 'best_day_share': 0.2,
            }})
            self.assertEqual(updated['wallets'][newbie]['state'], 'paper_test')
            self.assertEqual(updated['wallets'][weak]['state'], 'paused')
            with store.connect() as db:
                kept = db.execute('SELECT body FROM wallet_copy_positions').fetchone()[0]
            self.assertEqual(json.loads(kept)['pnl_micro'], -500_000)
            actions = {row['wallet']: row for row in store.get('wallet_selection_audit')}
            self.assertEqual(actions[weak]['action'], 'paused')
            self.assertEqual(actions[newbie]['action'], 'promoted')
            self.assertEqual(actions[newbie]['reason'], PROMOTE_REASON)

    def test_every_plus_wallet_is_copied(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 9_000_000
            state = bootstrap(store, now=now)
            extras = ['0x' + hex(i + 1)[2:].rjust(40, 'a') for i in range(4)]
            for wallet in extras:
                state['wallets'][wallet] = {
                    'wallet': wallet, 'state': 'observed', 'since': now - 5,
                }
            store.set('wallet_roster', state)
            store.set('wallet_observation_meta', {
                'version': 'copy-observe-v2', 'started_at': now - 10,
            })
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_observation_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)'
                )
                for i, wallet in enumerate(extras):
                    db.execute(
                        'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                        (str(i), wallet, json.dumps({
                            'policy': 'copy-observe-v2', 'status': 'SETTLED',
                            'opened': now - 20, 'closed_at': now - 10,
                            'pnl_micro': 1_000_000, 'market': f'm{i}', 'fee': 1000,
                        })),
                    )
            updated, changed = tick(store, now=now)
            for wallet in extras:
                self.assertEqual(updated['wallets'][wallet]['state'], 'paper_test')
                self.assertIn(wallet, changed)
            copying = [
                row['state'] for row in updated['wallets'].values()
                if row['state'] in ('paper_test', 'paper_active')
            ]
            self.assertGreater(len(copying), 3)

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

    def test_v1_roster_upgrades_without_resetting_wallets(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            wallet = '0x' + 'ab' * 20
            store.set('wallet_roster', {
                'spec': PREVIOUS_SPEC,
                'rules': RULES_V1,
                'updated_at': 10,
                'wallets': {wallet: {'wallet': wallet, 'state': 'paused', 'since': 4, 'reason': 'old'}},
            })
            state = bootstrap(store, now=50)
            self.assertEqual(state['spec'], SPEC)
            self.assertEqual(state['previous_spec'], PREVIOUS_SPEC)
            self.assertEqual(state['previous_rules']['paper_active_to_paused']['rolling_7d_net_usd'], -15.0)
            self.assertEqual(state['wallets'][wallet]['since'], 4)
            self.assertEqual(state['wallets'][wallet]['state'], 'paused')

    def test_v2_roster_upgrades_without_resetting_wallets(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            wallet = '0x' + 'cd' * 20
            store.set('wallet_roster', {
                'spec': SPEC_V2,
                'rules': RULES_V2,
                'previous_spec': PREVIOUS_SPEC,
                'previous_rules': RULES_V1,
                'updated_at': 10,
                'wallets': {wallet: {'wallet': wallet, 'state': 'paper_test', 'since': 4, 'reason': 'old'}},
            })
            state = bootstrap(store, now=50)
            self.assertEqual(state['spec'], SPEC)
            self.assertEqual(state['previous_spec'], SPEC_V2)
            self.assertEqual(state['previous_rules']['observed_to_paper_test']['max_best_day_share'], 0.70)
            self.assertEqual(state['rule_history'][0]['spec'], PREVIOUS_SPEC)
            self.assertEqual(state['wallets'][wallet]['since'], 4)
            self.assertEqual(state['wallets'][wallet]['state'], 'paper_test')

    def test_v1_observation_does_not_qualify_without_v2_results(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 5_000_000
            wallet = '0x' + 'ab' * 20
            started = now - 30 * 86400
            store.set('wallet_observation_meta', {
                'version': 'copy-observe-v2',
                'previous_version': 'copy-observe-v1',
                'paper_policy': 'copy-paper-v2',
                'started_at': started,
            })
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paused', 'since': now - 2 * 86400, 'reason': 'old pause',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_observation_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)'
                )
                for i in range(20):
                    db.execute(
                        'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                        (f'v1-{i}', wallet, json.dumps({
                            'policy': 'copy-observe-v1', 'status': 'SETTLED',
                            'opened': now - 86400, 'closed_at': now - 3600,
                            'pnl_micro': 1_000_000, 'market': f'm{i}', 'fee': 1000,
                        })),
                    )
            evidence = copy_evidence(store, wallet, now)
            self.assertEqual(evidence['our_trades'], 0)
            self.assertIsNone(evidence['copy_sim_net_usd'])
            self.assertFalse(can_observe_to_test(evidence))
            updated, changed = tick(store, now=now)
            self.assertEqual(changed, [])
            self.assertEqual(updated['wallets'][wallet]['state'], 'paused')

    def test_positive_copy_book_returns_from_pause(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + 'ab' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paused', 'since': now - 3600, 'reason': 'old pause',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                db.execute(
                    'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                    (json.dumps({
                        'wallet': wallet, 'status': 'SETTLED', 'opened': now - 86400,
                        'closed_at': now - 7200, 'pnl_micro': 14_520_000, 'market': 'btc-updown-5m-1',
                    }),),
                )
            updated, changed = tick(store, now=now)
            self.assertNotIn(wallet, changed)
            self.assertEqual(updated['wallets'][wallet]['state'], 'paused')

    def test_negative_period_pauses_even_when_older_trades_are_positive(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + 'cd' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paper_test', 'since': now - 60, 'reason': 'copying',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                for pnl, opened, market in (
                    (10_000_000, now - 86400, 'old'),
                    (-1_000_000, now - 30, 'new'),
                ):
                    db.execute(
                        'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                        (json.dumps({
                            'wallet': wallet, 'status': 'SETTLED', 'opened': opened,
                            'closed_at': opened + 10, 'pnl_micro': pnl, 'market': market,
                        }),),
                    )
            updated, changed = tick(store, now=now)
            self.assertIn(wallet, changed)
            self.assertEqual(updated['wallets'][wallet]['state'], 'paused')
            self.assertEqual(updated['wallets'][wallet]['reason'], PAUSE_REASON)

    def test_plus_period_keeps_copying_when_older_losses_are_outside_it(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + '11' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paper_test', 'since': now - 60, 'reason': 'copying',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                for pnl, opened, market in (
                    (-10_000_000, now - 86400, 'old'),
                    (1_000_000, now - 30, 'new'),
                ):
                    db.execute(
                        'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                        (json.dumps({
                            'wallet': wallet, 'status': 'SETTLED', 'opened': opened,
                            'closed_at': opened + 10, 'pnl_micro': pnl, 'market': market,
                        }),),
                    )
            updated, changed = tick(store, now=now)
            self.assertEqual(updated['wallets'][wallet]['state'], 'paper_test')

    def test_pause_is_visible_to_the_next_buy_on_the_same_connection(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + '22' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paper_test', 'since': now - 60, 'reason': 'copying',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                db.execute(
                    'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                    (json.dumps({
                        'wallet': wallet, 'status': 'SETTLED', 'opened': now - 10,
                        'closed_at': now, 'pnl_micro': -500_000, 'market': 'm',
                    }),),
                )
                self.assertTrue(pause_if_period_negative(db, wallet, now))
                self.assertEqual(buy_pause_reason(db, wallet, now), 'COPY_PAUSED')

    def test_plus_observation_opens_a_copy_without_waiting_for_candidate_stats(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + 'ef' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'observed', 'since': now - 3600, 'reason': 'watching',
            }
            store.set('wallet_roster', state)
            store.set('wallet_observation_meta', {
                'version': 'copy-observe-v2',
                'previous_version': 'copy-observe-v1',
                'started_at': now - 3600,
            })
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_observation_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)'
                )
                db.execute(
                    'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                    ('old', wallet, json.dumps({
                        'policy': 'copy-observe-v1', 'status': 'SETTLED',
                        'opened': now - 7200, 'closed_at': now - 7000,
                        'pnl_micro': 9_000_000, 'market': 'm1', 'fee': 1000,
                    })),
                )
            updated, changed = tick(store, now=now)
            self.assertIn(wallet, changed)
            self.assertEqual(updated['wallets'][wallet]['state'], 'paper_test')
            self.assertEqual(updated['wallets'][wallet]['reason'], PROMOTE_REASON)

    def test_negative_observation_stays_observed(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + '11' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'observed', 'since': now - 3600, 'reason': 'watching',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute(
                    'CREATE TABLE wallet_observation_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)'
                )
                db.execute(
                    'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                    ('down', wallet, json.dumps({
                        'policy': 'copy-observe-v2', 'status': 'SETTLED',
                        'opened': now - 100, 'closed_at': now - 10,
                        'pnl_micro': -2_000_000, 'market': 'm1', 'fee': 1000,
                    })),
                )
            updated, changed = tick(store, now=now)
            self.assertNotIn(wallet, changed)
            self.assertEqual(updated['wallets'][wallet]['state'], 'observed')

    def test_missing_copy_pnl_does_not_return_a_paused_wallet(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            now = 6_000_000
            wallet = '0x' + '22' * 20
            state = bootstrap(store, now=now)
            state['wallets'][wallet] = {
                'wallet': wallet, 'state': 'paused', 'since': now - 3600, 'reason': 'old pause',
            }
            store.set('wallet_roster', state)
            with store.connect() as db:
                db.execute('CREATE TABLE wallet_copy_positions (id INTEGER PRIMARY KEY, body TEXT)')
                db.execute(
                    'INSERT INTO wallet_copy_positions(body) VALUES (?)',
                    (json.dumps({
                        'wallet': wallet, 'status': 'SETTLED', 'opened': now - 100,
                        'closed_at': now - 10, 'pnl_micro': None, 'market': 'm1',
                    }),),
                )
            updated, changed = tick(store, now=now)
            self.assertNotIn(wallet, changed)
            self.assertEqual(updated['wallets'][wallet]['state'], 'paused')
