import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location('telegram_bot', ROOT / 'deploy' / 'telegram_bot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bot = load()
WALLET = '0x943cea746e701823b6902a6f4eaeed58207e77c2'


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send(self, chat, text):
        self.sent.append((chat, text))


def state(recent=(), journal=(), paused=False):
    return {'live_enabled': False, 'mitch_copy': {
        'recent': list(recent), 'journal': list(journal),
        'wallets': [{'wallet': WALLET, 'label': '0xdc27', 'paused': paused}],
    }}


class AlertTests(unittest.TestCase):
    def test_the_first_read_is_history_not_news(self):
        memory = {}
        buy = {'at': 1, 'wallet': WALLET, 'reason': 'MITCH_BUY', 'detail': {'market': 'm'}}
        self.assertEqual(bot.alerts(state([buy]), memory), [])
        self.assertEqual(bot.alerts(state([buy]), memory), [])

    def test_paper_trades_and_pauses_are_not_messages(self):
        # Damian, 17 Oct 2026: only what needs him now.
        memory = {}
        bot.alerts(state(), memory)
        buy = {'at': 2, 'wallet': WALLET, 'reason': 'MITCH_BUY', 'detail': {'market': 'btc-updown-15m-1'}}
        self.assertEqual(bot.alerts(state([buy], paused=True), memory), [])

    def test_a_live_error_is_alerted_once(self):
        memory = {'primed': True}
        st = dict(state(), mitch_live={'recent': [{'id': 'live:1', 'status': 'ERROR', 'error': 'not enough balance'}]})
        out = bot.alerts(st, memory)
        self.assertEqual(len(out), 1)
        self.assertIn('BŁĄD prawdziwego zlecenia', out[0])
        self.assertEqual(bot.alerts(st, memory), [])

    def test_real_money_alerts(self):
        memory = {'primed': True}
        live = {'mode': 'live', 'wallet': {'pusd': 170.0, 'pol': 10.7}, 'result': {'pnl_usd': '4.5'}, 'swept_usd': '0',
                'sweeps': [{'at': 100, 'stage': 'done', 'sent_micro': 6_120_000, 'tx': '0xabc'}],
                'recent': [{'id': i, 'side': 'BUY', 'status': 'NOT_FILLED', 'finished_at': 50 + i} for i in range(3)]}
        out = bot.alerts(dict(state(), mitch_live=live), memory, now=1000)
        self.assertTrue(any('6.12 USDC poszło na Kraken' in m for m in out))
        self.assertTrue(any('3 prawdziwe kupna z rzędu NIEWYKONANE' in m for m in out))
        self.assertEqual(bot.alerts(dict(state(), mitch_live=live), memory, now=1001), [])   # once each
        live['recent'] = [{'id': 9, 'side': 'BUY', 'status': 'FILLED', 'finished_at': 2000, 'closed': True,
                           'closed_at': 2100, 'pnl_usd': '2.5', 'won': True}]
        out = bot.alerts(dict(state(), mitch_live=live), memory, now=1000 + 3 * 3600)
        self.assertEqual(len(out), 1)
        self.assertIn('LIVE ostatnie 3 h: 1 kupna wykonane z 1, rozliczone 1 (1 wygranych) +2.50 USD', out[0])
        self.assertEqual(bot.alerts(dict(state(), mitch_live=dict(live, mode='dry')), {'primed': True}, now=99999), [])

    def test_live_flag_is_always_alerted(self):
        memory = {'primed': True}
        out = bot.alerts(dict(state(), live_enabled=True), memory)
        self.assertTrue(any('live_enabled' in text for text in out))


class MarketGuardTests(unittest.TestCase):
    def test_a_sharp_move_alerts_once_per_cooldown(self):
        memory = {}
        now = 1_000_000.0
        self.assertEqual(bot.market_moves(memory, 80000.0, now), [])
        out = bot.market_moves(memory, 80000.0 * 1.012, now + 300)
        self.assertEqual(len(out), 1)
        self.assertIn('+1.20% w 5 min', out[0])
        self.assertEqual(bot.market_moves(memory, 80000.0 * 1.013, now + 330), [])

    def test_calendar_warns_once_an_hour_ahead(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmp:
            bot.CALENDAR = Path(tmp) / 'cal.json'
            bot.MARKET_LOG = Path(tmp) / 'events.jsonl'
            bot.CALENDAR.write_text(_json.dumps({'events': [{'name': 'CPI', 'at': 10_000.0, 'note': 'x'}]}))
            memory = {}
            self.assertEqual(bot.calendar_alerts(memory, 10_000 - 4000), [])
            self.assertEqual(len(bot.calendar_alerts(memory, 10_000 - 3000)), 1)
            self.assertEqual(bot.calendar_alerts(memory, 10_000 - 2000), [])
            self.assertEqual(bot.calendar_alerts(memory, 10_000 - 300), [])
            self.assertTrue(bot.MARKET_LOG.exists())


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bot.PAUSE = Path(self.tmp.name) / 'data' / 'PAUSE'
        bot.QUALIFIER_OFF = Path(self.tmp.name) / 'data' / 'QUALIFIER_OFF'
        bot.MITCH_OFF = Path(self.tmp.name) / 'data' / 'MITCH_OFF'
        bot.LIVE_STOP = Path(self.tmp.name) / 'data' / 'LIVE_STOP'

    def test_qualifier_and_mitch_switches(self):
        tg = FakeTelegram()
        bot.handle('/kwalifikator_stop', 1, tg, allowed={1})
        self.assertTrue(bot.QUALIFIER_OFF.exists())
        bot.handle('/mitch_stop', 1, tg, allowed={1})
        self.assertTrue(bot.MITCH_OFF.exists())
        bot.handle('/kwalifikator_start', 1, tg, allowed={1})
        bot.handle('/mitch_start', 1, tg, allowed={1})
        self.assertFalse(bot.QUALIFIER_OFF.exists() or bot.MITCH_OFF.exists())
        self.assertIn('WYŁĄCZONE', tg.sent[0][1])
        bot.handle('/kwalifikator_stop', 99, tg, allowed={1})
        self.assertFalse(bot.QUALIFIER_OFF.exists())

    def test_live_stop_and_start(self):
        tg = FakeTelegram()
        bot.handle('/live_stop', 1, tg, allowed={1})
        self.assertTrue(bot.LIVE_STOP.exists())
        self.assertIn('WSTRZYMANE', tg.sent[-1][1])
        bot.handle('/live_stop', 99, tg, allowed={1})   # a stranger changes nothing
        bot.handle('/live_start', 1, tg, allowed={1})
        self.assertFalse(bot.LIVE_STOP.exists())

    def test_live_text(self):
        st = {'mitch_live': {'mode': 'dry', 'wallet': {'pusd': 9.99, 'pol': 10.8},
                             'limits': {'max_exposure_usd': '30', 'day_loss_stop_usd': '20'},
                             'exposure_usd': '0', 'day_loss_usd': '0', 'counts': {'DRY_SIGNED': 2},
                             'recent': [{'finished_at': 1792232100, 'side': 'BUY', 'amount_usd': '1.30',
                                         'source_price': '0.16', 'status': 'DRY_SIGNED', 'from_source_ms': 324.9}]}}
        text = bot.live_text(st)
        self.assertIn('TEST', text)
        self.assertIn('9.99 pUSD', text)
        self.assertIn('0.32 s od Mitcha', text)

    def test_text_views(self):
        st = {'mitch_copy': {'wallets': [{'wallet': WALLET, 'label': '0xdc27', 'paused': True,
                                          'pause_reason': 'Minus dzisiaj.'}],
                             'period_reasons': {'MITCH_BUY': 2, 'LATE_BUY_NOT_COPIED': 5},
                             'period_events': [{'at': 1_791_600_000, 'wallet': WALLET, 'reason': 'MITCH_BUY',
                                                'side': 'BUY', 'total_ms': 240}]},
              'accounts': [{'id': 'copy-0xaaaa1111', 'pnl': 3.5, 'trades': 4},
                           {'id': 'copy-0xbbbb2222', 'pnl': -9.0, 'trades': 7}],
              'wallet_roster': {'wallets': {'a': {'state': 'paper_test'}, 'b': {'state': 'paused'}}}}
        self.assertIn('240 ms', bot.copies_text(st))
        self.assertIn('kupiono', bot.copies_text(st))
        self.assertIn('Minus dzisiaj', bot.pauses_text(st))
        detail = bot.wallets_detail_text(st)
        self.assertIn('Na plusie 1 z 2', detail)
        self.assertIn('aaaa1111', detail)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_stranger_gets_only_his_chat_id(self):
        tg = FakeTelegram()
        bot.handle('/start', 99, tg, allowed={1})
        bot.handle('/stop', 99, tg, allowed={1})
        self.assertEqual(len(tg.sent), 1)
        self.assertIn('99', tg.sent[0][1])
        self.assertFalse(bot.PAUSE.exists())

    def test_stop_and_resume_use_the_pause_file(self):
        tg = FakeTelegram()
        bot.handle('/stop', 1, tg, allowed={1})
        self.assertTrue(bot.PAUSE.exists())
        bot.handle('/wznow', 1, tg, allowed={1})
        self.assertFalse(bot.PAUSE.exists())


class ManualPause(unittest.TestCase):
    def test_pause_and_resume_one_wallet_by_label(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            old = bot.MITCH_MANUAL
            bot.MITCH_MANUAL = Path(tmp) / 'mitch_manual_pauses.json'
            try:
                self.assertIn('wstrzymane', bot.manual_pause('dc27', 'tydzień minus', 1, True))
                body = json.loads(bot.MITCH_MANUAL.read_text())
                self.assertEqual(body['wallets']['0x943cea746e701823b6902a6f4eaeed58207e77c2']['reason'], 'tydzień minus')
                self.assertIn('wraca', bot.manual_pause('0xdc27', '', 1, False))
                self.assertEqual(json.loads(bot.MITCH_MANUAL.read_text())['wallets'], {})
                self.assertIn('Nie znam', bot.manual_pause('nobody', '', 1, True))
            finally:
                bot.MITCH_MANUAL = old

    def test_review_lists_flags_and_desk_cash(self):
        state = {'mitch_copy': {'desk_cash_usd': 2400.5, 'wallets': [
            {'wallet': '0xa82365c8e854728c472812fba6202ca125386215', 'label': 'mihaXd', 'week_net_usd': -4.2,
             'week_closed': 9, 'period_net_micro': -4_200_000, 'review': ['minus na kopiach przez ostatni tydzień']}]}}
        text = bot.review_text(state)
        self.assertIn('mihaXd', text)
        self.assertIn('do sprawdzenia', text)
        self.assertIn('2400.50', text)


class WindowReport(unittest.TestCase):
    def test_window_text_like_mitch(self):
        w = {'market': 'btc-updown-15m-1791627000', 'fills': 14, 'wallets': ['0xdc27'], 'done': True,
             'pnl_micro': 84_900_000, 'sides': {'Down': {'in_micro': 55_000_000, 'shares_micro': 140_000_000,
             'avg': 0.3929, 'if_wins_micro': 140_000_000, 'if_wins_net_micro': 85_000_000}}}
        text = bot.window_text(w)
        self.assertIn('14 kupna', text)
        self.assertIn('Down: 55.00 USD w, 140 akcji, śr. 39¢', text)
        self.assertIn('WYGRANA', text)

    def test_a_finished_window_is_not_a_message(self):
        state = {'mitch_copy': {'windows': [{'market': 'btc-updown-15m-1', 'done': True, 'fills': 1,
                                             'sides': {}, 'pnl_micro': -1_000_000, 'wallets': []}]}}
        self.assertEqual(bot.alerts(state, {'primed': True}), [])


class Brake(unittest.TestCase):
    def test_a_warm_up_brake_is_silent_a_long_one_is_sent_once(self):
        memory = {'primed': True}
        on = {'mitch_copy': {'brake': {'on': True, 'reason': 'rozgrzewka'}}}
        self.assertEqual(bot.alerts(on, memory, now=1000), [])
        self.assertEqual(bot.alerts({'mitch_copy': {'brake': {'on': False}}}, memory, now=1120), [])   # 2 min: silent
        bot.alerts(on, memory, now=2000)
        late = bot.alerts(on, memory, now=2000 + bot.BRAKE_ALERT_AFTER_S)
        self.assertTrue(any('HAMULEC' in m for m in late))
        self.assertEqual(bot.alerts(on, memory, now=2600), [])
        off = bot.alerts({'mitch_copy': {'brake': {'on': False}}}, memory, now=2700)
        self.assertTrue(any('zdjęty' in m for m in off))


if __name__ == '__main__':
    unittest.main()
