import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.strategy_control import DEFAULT_PAUSED, is_paused, pauses, set_paused


class StrategyControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lab.db')

    def tearDown(self):
        self.temp.cleanup()

    def test_every_own_strategy_starts_paused(self):
        # 9 Oct 2026: early-v1 lost after fees like the others.
        state = pauses(self.store)
        self.assertTrue(state['mid-window-v1'])
        self.assertTrue(state['mid-window-v2'])
        self.assertTrue(state['early-v1'])
        self.assertTrue(is_paused(self.store, 'early-v1'))
        self.assertNotIn('late-v1', state)

    def test_toggle_persists(self):
        set_paused(self.store, 'mid-window-v1', False)
        self.assertFalse(is_paused(self.store, 'mid-window-v1'))
        self.assertTrue(DEFAULT_PAUSED['mid-window-v1'])
        set_paused(self.store, 'early-v1', True)
        self.assertTrue(is_paused(self.store, 'early-v1'))

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(ValueError):
            set_paused(self.store, 'copy-anything', True)

    def test_losing_copy_wallets_start_paused_and_winner_stays_on(self):
        state = pauses(self.store)
        self.assertTrue(state['copy-0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589'])
        self.assertTrue(state['copy-0x943cea746e701823b6902a6f4eaeed58207e77c2'])
        self.assertTrue(state['copy-0xeebde7a0e019a63e6b476eb425505b7b3e6eba30'])
        self.assertFalse(state['copy-0x16217458b59b3458149918058754cd234096b159'])

    def test_discovered_copy_id_can_be_paused(self):
        name = 'copy-0x' + ('cd' * 20)
        self.assertFalse(is_paused(self.store, name))
        set_paused(self.store, name, True)
        self.assertTrue(is_paused(self.store, name))
        set_paused(self.store, name, False)
        self.assertFalse(is_paused(self.store, name))

    def test_copy_wallet_can_be_toggled(self):
        name = 'copy-0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589'
        self.assertTrue(is_paused(self.store, name))
        set_paused(self.store, name, False)
        self.assertFalse(is_paused(self.store, name))
