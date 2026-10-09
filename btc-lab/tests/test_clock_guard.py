import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'clock_guard', Path(__file__).parents[1] / 'deploy/clock_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

SAMPLE = '+2.343002 +/- 0.003595 time.apple.com 17.253.38.35\n'
HEALTHY = '+0.011643 +/- 0.004514 time.apple.com 17.253.38.43\n'

class ClockGuardTests(unittest.TestCase):
    def test_parses_sntp_offset_and_ignores_earlier_lines(self):
        offset, uncertainty = guard.parse_sntp('sntp: kisstime\n' + SAMPLE)
        self.assertAlmostEqual(offset, 2.343002)
        self.assertAlmostEqual(uncertainty, 0.003595)

    def test_large_agreed_offset_steps(self):
        self.assertEqual(guard.action_for((2.34, 0.004), (2.30, 0.004)), 'step')
        self.assertEqual(guard.action_for((-2.10, 0.004), (-2.05, 0.004)), 'step')

    def test_healthy_clock_is_left_alone(self):
        self.assertEqual(guard.action_for((0.012, 0.004), (0.011, 0.004)), 'ok')

    def test_split_or_fuzzy_reading_does_not_step(self):
        """One bad packet is how timed jumped the clock. Do not repeat it."""
        self.assertEqual(guard.action_for((2.34, 0.004), (0.01, 0.004)), 'hold')
        self.assertEqual(guard.action_for((2.34, 0.20), (2.30, 0.20)), 'hold')

    def test_offset_line_wins_over_a_trailing_root_warning(self):
        text = SAMPLE + 'sntp: bind: Address already in use\n'
        self.assertAlmostEqual(guard.parse_sntp(text)[0], 2.343002)

    def test_real_sntp_line_shapes(self):
        self.assertAlmostEqual(guard.parse_sntp(HEALTHY)[0], 0.011643)
        self.assertAlmostEqual(guard.parse_sntp(SAMPLE)[0], 2.343002)

if __name__ == '__main__':
    unittest.main()
