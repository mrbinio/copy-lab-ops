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
        self.assertIsNone(r['counterfactual_pnl']);self.engine.publish('TEST')
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
