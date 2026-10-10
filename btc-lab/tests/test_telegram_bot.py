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

    def test_a_new_buy_a_close_and_a_pause_are_sent_once(self):
        memory = {}
        bot.alerts(state(), memory)
        buy = {'at': 2, 'wallet': WALLET, 'reason': 'MITCH_BUY',
               'detail': {'market': 'btc-updown-15m-1', 'timing': {'total_ms': 240.0}}}
        skip = {'at': 3, 'wallet': WALLET, 'reason': 'LATE_BUY_NOT_COPIED', 'detail': {}}
        close = {'at': 4, 'wallet': WALLET, 'slug': 'btc-updown-15m-1', 'pnl_micro': -1_500_000}
        out = bot.alerts(state([buy, skip], [close], paused=True), memory)
        self.assertEqual(len(out), 3)
        self.assertIn('KUPNO', out[0])
        self.assertIn('240 ms', out[0])
        self.assertIn('-1.50', out[1])
        self.assertIn('PAUZA', out[2])
        self.assertEqual(bot.alerts(state([buy, skip], [close], paused=True), memory), [])

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

    def test_calendar_warns_at_60_and_10_minutes(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmp:
            bot.CALENDAR = Path(tmp) / 'cal.json'
            bot.MARKET_LOG = Path(tmp) / 'events.jsonl'
            bot.CALENDAR.write_text(_json.dumps({'events': [{'name': 'CPI', 'at': 10_000.0, 'note': 'x'}]}))
            memory = {}
            self.assertEqual(bot.calendar_alerts(memory, 10_000 - 4000), [])
            self.assertEqual(len(bot.calendar_alerts(memory, 10_000 - 3000)), 1)
            self.assertEqual(bot.calendar_alerts(memory, 10_000 - 2000), [])
            self.assertEqual(len(bot.calendar_alerts(memory, 10_000 - 300)), 1)
            self.assertTrue(bot.MARKET_LOG.exists())


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bot.PAUSE = Path(self.tmp.name) / 'data' / 'PAUSE'

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


if __name__ == '__main__':
    unittest.main()
