import asyncio
import test_wallet_copy as fixtures

class SkipReviewTests(fixtures.CopyTests):
    def test_skip_review_records_evidence_and_no_profit(self):
        self.now=1102;self.ask='.8';row=self.row();self.process(row)
        self.assertEqual(self.engine.skip_summary()['total'],0)
        self.assertEqual(self.engine.skip_summary()['recent'],[])
        self.assertEqual(self.reason(),'COPIED_BUY')
    def test_review_mismatch_and_unofficial_result(self):
        self.now=1102;self.ask='.8';self.process(self.row());self.now=2000
        self.assertEqual(self.engine.skip_summary()['total'],0)
        self.assertEqual(self.engine.skip_summary()['recent'],[])
        asyncio.run(self.engine.review_skips())
        self.assertEqual(self.engine.skip_summary()['total'],0)

    def test_shadow_no_depth_cannot_invent_profit(self):
        self.now=1102;self.ask='.8';self.depth='1';self.process(self.row())
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['shadow']['status'],'NO_FULL_FILL')
        self.assertIsNone(r['counterfactual_pnl'])
    def test_shadow_winner_uses_actual_shares_and_fee(self):
        self.buy();self.now+=2;self.ask='.8';self.process(self.row('dup'))
        self.official['tokens'][0]['winner']=True;self.official['tokens'][1]['winner']=False
        self.now=2000;asyncio.run(self.engine.review_skips())
        r=self.engine.skip_summary()['recent'][0]
        self.assertEqual(r['status'],'RESOLVED')

    def test_shadow_stale_quote_stays_unknown(self):
        self.now=1102;self.ask='.8';self.stale=True;self.process(self.row())
        self.assertEqual(self.engine.skip_summary()['total'],0)
        self.assertEqual(self.engine.skip_summary()['recent'],[])
        self.assertEqual(self.reason(),'COPIED_BUY')
