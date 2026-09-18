import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('macos_launch',Path(__file__).resolve().parents[1]/'deploy/macos_launch.py')
launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)

def result(code=0,stdout='',stderr=''):
    return SimpleNamespace(returncode=code,stdout=stdout,stderr=stderr)

class LaunchTests(unittest.TestCase):
    def test_retries_bootstrap_after_enable(self):
        with patch.object(launch,'command',side_effect=[result(),result(),result(5,stderr='I/O'),result()]) as cmd,patch.object(launch,'registered',return_value=False),patch.object(launch.time,'sleep'):
            launch.start_service('gui/501/com.btc-lab.paper',Path('/tmp/test.plist'))
            self.assertEqual(cmd.call_args_list[1].args,('/bin/launchctl','enable','gui/501/com.btc-lab.paper'))
            self.assertEqual(sum(c.args[1]=='bootstrap' for c in cmd.call_args_list),2)

    def test_invalid_plist_never_bootstrapped(self):
        with patch.object(launch,'command',return_value=result(1,stderr='invalid')) as cmd:
            with self.assertRaisesRegex(RuntimeError,'plist'):launch.start_service('gui/501/test',Path('/tmp/test.plist'))
            self.assertEqual(cmd.call_count,1)

    def test_stop_waits_for_registration_to_disappear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            with patch.object(launch,'registered',side_effect=[True,True,False]),patch.object(launch,'command',return_value=result()) as cmd,patch.object(launch.time,'sleep') as sleep:
                launch.stop_service('gui/501/test',root)
                cmd.assert_called_once_with('/bin/launchctl','bootout','gui/501/test')
                sleep.assert_called_once()

    def test_bootstrap_failures_are_bounded(self):
        with patch.object(launch,'command',side_effect=[result(),result(),result(5,stderr='I/O'),result(5,stderr='I/O'),result(5,stderr='I/O')]),patch.object(launch,'registered',return_value=False),patch.object(launch.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'bootstrap'):launch.start_service('gui/501/test',Path('/tmp/test.plist'))
