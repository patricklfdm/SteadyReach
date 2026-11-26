"""Regressions for space accounting, previewed diagnostics and offline distribution."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch

from ras_workflow import queue_operations as ops
from ras_workflow.common import ROOT, digest, save
from scripts import deployment, software_release


class QueueRecoveryControls(unittest.TestCase):
    def setUp(self):
        (ROOT/'status').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'status')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root/'attempt1'
        self.second = self.root/'attempt2'
        self.first.mkdir()
        self.second.mkdir()

    def test_outstanding_space_is_excluded_and_released(self):
        fake_volume = shutil._ntuple_diskusage(1000, 800, 200)
        with patch.object(ops.shutil, 'disk_usage', return_value=fake_volume):
            with ops.reserve(self.first, 150, root=self.root):
                with self.assertRaises(ops.SpaceUnavailable):
                    with ops.reserve(self.second, 60, root=self.root):
                        self.fail('Space was promised twice')
            with ops.reserve(self.second, 180, root=self.root) as result:
                self.assertEqual(result['other_reserved_bytes'], 0)

    def test_closed_owner_lease_reclaimed(self):
        registry = self.root/'status/queue_space'
        save(registry/'old.json', dict(bytes=2**60, lease='attempt1/space.lock'))
        with ops.reserve(self.second, 1, root=self.root) as record:
            self.assertEqual(record['other_reserved_bytes'], 0)
        self.assertFalse((registry/'old.json').exists())

    def test_private_error_text_and_identifiers_stay_local(self):
        state = self.root/'queue_state.json'
        attempt = dict(status='NEEDS_EXPORT', error='Confidential field.pdf', folder=str(self.root),
                       stage_seconds=dict(solver=1.5, owner='private'))
        save(state, dict(jobs={'secret_site':[attempt]}))
        name = self.root.relative_to(ROOT)
        preview = ops.support(name)
        text = json.dumps(preview)
        for sensitive in ('Confidential','secret_site','private',str(self.root)):
            self.assertNotIn(sensitive,text)
        bundle = self.root/'support.zip'
        ops.export_support(name,bundle,digest(preview))
        with ZipFile(bundle) as archive:
            self.assertEqual(json.loads(archive.read('Support.json')), preview)
        save(state, dict(jobs={'secret_site':[dict(status='COMPLETED')]}))
        with self.assertRaisesRegex(ValueError,'Preview'):
            ops.export_support(name,self.root/'next.zip',digest(preview))
        self.assertFalse((self.root/'next.zip').exists())


class DistributionChecks(unittest.TestCase):
    def test_empty_wheelhouse_identifies_lock_entry(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, 'Missing locked wheels: example'):
                software_release.wheel_inventory(Path(name), 'example==1.0')

    def test_installer_cannot_be_the_upgrade_backup(self):
        with tempfile.TemporaryDirectory() as name:
            here = Path(name)
            with self.assertRaisesRegex(ValueError,'separate'):
                deployment.require_distinct(here/'old',here/'new',here/'control',here/'old/archive.zip')

    def test_partial_installation_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as name:
            here = Path(name)
            (here/'INSTALL_IN_PROGRESS.json').write_text('{}')
            with patch.object(software_release,'verify',return_value={}):
                with self.assertRaisesRegex(ValueError,'did not finish'):
                    software_release.verify_installation(here,here/'release',here/'trusted_key')

if __name__=='__main__':
    unittest.main()
