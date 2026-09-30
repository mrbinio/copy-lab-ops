import asyncio
import test_wallet_copy as fixtures

class SkipReviewTests(fixtures.CopyTests):
    def test_skip_review_records_evidence_and_no_profit(self):
        self.now=1102;self.ask='.8';row=self.row();self.process(row)
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['detection_delay'],1);self.assertIsNotNone(r['decision_book'])
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['status'],'RESOLVED');self.assertFalse(r['source_side_won'])
        self.assertLess(r['counterfactual_pnl'],0);self.assertEqual(r['shadow']['status'],'SETTLED');self.engine.publish('TEST')
        self.assertEqual(self.state()['accounts'][0]['cash'],500)
        self.process(row);self.assertEqual(self.engine.skip_summary()['total'],1)
    def test_review_mismatch_and_unofficial_result(self):
        self.now=1102;self.ask='.8';self.process(self.row());self.now=2000
        self.official['condition_id']='wrong';asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['status'],'PENDING');self.assertIn('MISMATCH',r['error'])
        self.now+=61;self.official['condition_id']='condition';self.official['closed']=False
        asyncio.run(self.engine.review_skips())
        self.assertEqual(self.engine.skip_summary()['recent'][0]['status'],'PENDING')

    def test_shadow_no_depth_cannot_invent_profit(self):
        self.now=1102;self.ask='.8';self.depth='1';self.process(self.row())
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['shadow']['status'],'NO_FULL_FILL')
        self.assertIsNone(r['counterfactual_pnl'])
    def test_shadow_winner_uses_actual_shares_and_fee(self):
        self.now=1102;self.ask='.8';self.process(self.row())
        self.official['tokens'][0]['winner']=True;self.official['tokens'][1]['winner']=False
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0];f=r['shadow']['fill']
        self.assertEqual(r['shadow']['pnl_micro'],f['shares']-f['cost']-f['fee'])
        self.assertNotEqual(f['vwap'],.59)

    def test_shadow_stale_quote_stays_unknown(self):
        self.now=1102;self.ask='.8';self.stale=True;self.process(self.row())
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['shadow']['status'],'UNAVAILABLE')
        self.assertIsNone(r['counterfactual_pnl'])
