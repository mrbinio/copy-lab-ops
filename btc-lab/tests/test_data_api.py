import unittest

from lab.data_api import fetch_all, fetch_rows, page, v1_row

# Same trade, read live from v1 and v2 on 9 Oct 2026 (trimmed).
V2_ACTIVITY = {
    'proxy_wallet': '0x943cea746e701823b6902a6f4eaeed58207e77c2', 'timestamp': 1791539977,
    'condition_id': '0xa1e4', 'type': 'TRADE', 'size': 12.407408, 'usdc_size': 3.52118,
    'transaction_hash': '0x7684', 'price': 0.2699999871, 'token_id': '6890', 'side': 'BUY',
    'outcome_index': 0, 'slug': 'btc-updown-5m-1791539700', 'event_slug': 'btc-updown-5m-1791539700',
}


class DataApiTests(unittest.TestCase):
    def test_v2_activity_reads_like_v1(self):
        row = v1_row(V2_ACTIVITY)
        for key, value in {'proxyWallet': V2_ACTIVITY['proxy_wallet'], 'conditionId': '0xa1e4',
                           'usdcSize': 3.52118, 'transactionHash': '0x7684', 'asset': '6890',
                           'outcomeIndex': 0, 'eventSlug': 'btc-updown-5m-1791539700',
                           'side': 'BUY', 'size': 12.407408, 'timestamp': 1791539977}.items():
            self.assertEqual(row[key], value, key)

    def test_positions_and_leaderboard(self):
        self.assertEqual(v1_row({'token_id': 't', 'current_size': 25.0})['size'], 25.0)
        lead = v1_row({'rank': 1, 'user_id': '0xabc', 'pnl': 1.0, 'volume': 2.0, 'user_name': 'x'})
        self.assertEqual((lead['proxyWallet'], lead['vol'], lead['userName']), ('0xabc', 2.0, 'x'))

    def test_cursor_pages_until_has_more_is_false(self):
        pages = [
            {'data': [V2_ACTIVITY], 'pagination': {'has_more': True, 'next_cursor': 'c1'}},
            {'data': [V2_ACTIVITY], 'pagination': {'has_more': False, 'next_cursor': 'c2'}},
        ]
        seen = []

        def fetch(url):
            seen.append(url)
            return pages[len(seen) - 1]

        rows, complete = fetch_all(fetch, 'activity', 5, user='0xw', limit=500)
        self.assertTrue(complete)
        self.assertEqual(len(rows), 2)
        self.assertIn('/v2/activity?', seen[0])
        self.assertNotIn('cursor', seen[0])
        self.assertIn('cursor=c1', seen[1])

    def test_page_cap_is_not_complete(self):
        endless = {'data': [], 'pagination': {'has_more': True, 'next_cursor': 'x'}}
        rows, complete = fetch_all(lambda url: endless, 'activity', 3)
        self.assertFalse(complete)

    def test_a_bare_list_and_a_bad_answer(self):
        self.assertEqual(page([{'a': 1}]), ([{'a': 1}], None))
        with self.assertRaises(ValueError):
            page('nope')
        self.assertEqual(fetch_rows(lambda url: {'data': None}, 'activity'), ([], None))


if __name__ == '__main__':
    unittest.main()
