import gzip
import json
import tempfile
import unittest
from pathlib import Path

from lab.hires_recorder import Sink, compact_polymarket, window_tokens


def change(price, side, bb, ba, token='1111222233334444'):
    return {'asset_id': token, 'price': price, 'size': '10', 'side': side, 'best_bid': bb, 'best_ask': ba}


class CompactTests(unittest.TestCase):
    def test_top_of_book_kept_depth_dropped(self):
        tops = {}
        raw = json.dumps([{'event_type': 'price_change', 'timestamp': '1', 'price_changes': [
            change('0.48', 'BUY', '0.48', '0.50'),   # at best bid: kept
            change('0.10', 'BUY', '0.48', '0.50'),   # deep, top unchanged: dropped
            change('0.50', 'SELL', '0.48', '0.50'),  # at best ask: kept
            change('0.30', 'BUY', '0.49', '0.50'),   # deep but best bid moved: kept
        ]}])
        lines = compact_polymarket(raw, 7, tops)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0].split('\t')[:3], ['7', 'PC', '222233334444'])

    def test_other_events_stay_raw(self):
        self.assertIsNone(compact_polymarket(json.dumps({'event_type': 'last_trade_price'}), 1, {}))
        self.assertIsNone(compact_polymarket('not json', 1, {}))


class SinkTests(unittest.TestCase):
    def test_hourly_files_limits_and_disk_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = [86400 * 30 + 3600 * 5]
            free = [100 * 1024 ** 3]
            sink = Sink(Path(tmp) / 'hires', clock=lambda: clock[0],
                        disk=lambda p: type('D', (), {'free': free[0]})())
            self.assertTrue(sink.write('binance', '{"a":1}', 5))
            sink.write_line('polymarket', '5\tPC\tx')
            clock[0] += 3600
            sink.write('binance', '{"a":2}', 6)
            sink.close()
            files = sorted(p.name for p in (Path(tmp) / 'hires').rglob('*.gz'))
            self.assertEqual(files, ['05-binance.jsonl.gz', '05-polymarket.jsonl.gz', '06-binance.jsonl.gz'])
            first = next((Path(tmp) / 'hires').rglob('05-binance.jsonl.gz'))
            self.assertEqual(gzip.open(first, 'rt').read(), '5\t{"a":1}\n')
            old = Path(tmp) / 'hires' / '1970-01-02'
            old.mkdir()
            free[0] = 1024 ** 3
            sink.housekeep()
            self.assertFalse(old.exists())
            self.assertEqual(sink.paused, 'disk_low')
            self.assertFalse(sink.write('binance', '{}'))


class TokenTests(unittest.TestCase):
    def test_current_and_next_window_for_5m_and_15m(self):
        asked = []

        def fetch(url):
            asked.append(url.rsplit('/', 1)[1])
            slug = url.rsplit('/', 1)[1]
            return {'clobTokenIds': json.dumps(['u' + slug, 'd' + slug])}

        tokens = window_tokens(fetch, now=1800)
        self.assertEqual(asked, ['btc-updown-5m-1800', 'btc-updown-5m-2100', 'btc-updown-15m-1800', 'btc-updown-15m-2700'])
        self.assertEqual(len(tokens), 8)


if __name__ == '__main__':
    unittest.main()
