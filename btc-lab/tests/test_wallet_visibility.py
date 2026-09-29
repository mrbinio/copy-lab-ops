import asyncio
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_observer import WalletObserver, WALLETS
from lab.wallet_discovery import WalletDiscovery

class WalletVisibilityTests(unittest.TestCase):
    def test_snapshot_missing_and_observed_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'lab.db')
            self.assertEqual([w['status'] for w in store.snapshot()['wallet_observer']],['NOT_STARTED']*3)
            obs=WalletObserver(store,None)
            obs.ingest(WALLETS[0],[{'proxyWallet':WALLETS[0],'timestamp':100,'transactionHash':'test','type':'TRADE','side':'BUY','price':.6,'size':10,'title':'BTC'}],101)
            store.set('wallet_observer:'+WALLETS[0],{'wallet':WALLETS[0],'status':'POLL_OK','checked_at':101,'unique_fingerprints':1})
            snapshot=store.snapshot()
            self.assertEqual(snapshot['wallet_observer'][0]['unique_fingerprints'],1)
            self.assertEqual(snapshot['wallet_activity_recent'][0]['side'],'BUY')
            self.assertEqual(snapshot['wallet_activity_recent'][0]['first_seen'],101)
            self.assertTrue(all(a['trades']==0 for a in snapshot['accounts']))

    def test_discovery_intersection_and_error_retains_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'lab.db')
            calls=[]
            def fetch(url):
                calls.append(url)
                return [{'proxyWallet':WALLETS[0],'pnl':10,'vol':100},
                        {'proxyWallet':WALLETS[1],'pnl':-1 if 'MONTH' in url else 10,'vol':100}]
            discovery=WalletDiscovery(store,fetch)
            asyncio.run(discovery.scan())
            state=store.get('wallet_discovery',{})
            self.assertEqual(len(state['candidates']),1)
            self.assertFalse(state['copy_enabled'])
            self.assertTrue(all('category=CRYPTO' in c for c in calls))
            self.assertEqual(store.snapshot()['wallet_discovery'],state)
            def fail(url):raise ValueError('temporary error')
            discovery.fetch=fail
            asyncio.run(discovery.scan())
            error=store.get('wallet_discovery',{})
            self.assertEqual(error['status'],'ERROR')
            self.assertEqual(error['last_success_at'],state['last_success_at'])
            self.assertEqual(error['candidates'],state['candidates'])

    def test_invalid_leaderboard_rejected(self):
        for rows in ({},[{'proxyWallet':'bad','pnl':1,'vol':1}],
                     [{'proxyWallet':WALLETS[0],'pnl':float('nan'),'vol':1}]):
            with self.assertRaises(ValueError):WalletDiscovery.parse(rows)

    def test_eth_does_not_claim_wallet_observer(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(Store(Path(d)/'eth.db',asset='ETH').snapshot()['wallet_observer'],[])
