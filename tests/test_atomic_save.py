import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ras_workflow import common


def locked(code):
    error=PermissionError('Test-only Windows file contention')
    error.winerror=code
    return error


class AtomicSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.json'
        common.save(self.path,{'old':True})

    def test_transient_sharing_and_lock_violations_retry_atomic_replacement(self):
        for code in (32,33):
            attempts=[];real=common.os.replace
            def replace(source,target):
                attempts.append(source)
                if len(attempts)<3:raise locked(code)
                real(source,target)
            with patch.object(common.os,'replace',side_effect=replace),patch.object(common.time,'sleep') as sleep:
                common.save(self.path,{'new':code})
            self.assertEqual(common.read(self.path),{'new':code})
            self.assertEqual(len(attempts),3);self.assertEqual(len(set(attempts)),1)
            self.assertEqual(sleep.call_count,2)
            self.assertFalse(list(self.path.parent.glob('*.partial')))

    def test_persistent_lock_is_bounded_and_preserves_previous_file(self):
        with patch.object(common.os,'replace',side_effect=locked(32)) as replace,patch.object(common.time,'sleep') as sleep:
            with self.assertRaises(PermissionError):common.save(self.path,{'new':True})
        self.assertEqual(replace.call_count,6);self.assertEqual(sleep.call_count,5)
        self.assertEqual(common.read(self.path),{'old':True})
        self.assertEqual(len(list(self.path.parent.glob('*.partial'))),1)

    def test_access_denied_is_reported_immediately(self):
        with patch.object(common.os,'replace',side_effect=locked(5)) as replace,patch.object(common.time,'sleep') as sleep:
            with self.assertRaises(PermissionError):common.save(self.path,{'new':True})
        replace.assert_called_once();sleep.assert_not_called()
        self.assertEqual(common.read(self.path),{'old':True})

    def test_invalid_json_never_replaces_saved_state(self):
        with self.assertRaises(ValueError):common.save(self.path,{'value':float('nan')})
        self.assertEqual(common.read(self.path),{'old':True})


if __name__=='__main__':unittest.main()
