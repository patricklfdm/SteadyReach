import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ras_workflow.common import save
from ras_workflow.storage_inventory import inspect
from ras_workflow.storage_capacity import estimate


class StorageForecast(unittest.TestCase):
    def test_shared_reference_changes_without_size_or_mtime_change(self):
        with TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            for key in ('site_a','site_b'):
                save(root/'projects'/key/'app.json',dict(id=key,title=key,revision=1))
            item='projects/site_a/exports/file'
            dest=root/item
            dest.parent.mkdir()
            dest.write_text('protected on second scan')
            peer=root/'projects/site_b/ref.JSON'
            peer.write_text('{"source":"projects/site_c/exports/file"}')
            s=peer.stat()
            self.assertIn(item,inspect(root,'site_a')['reclaim'])
            peer.write_text('{"source":"projects/site_a/exports/file"}')
            os.utime(peer,ns=(s.st_atime_ns,s.st_mtime_ns))
            result=inspect(root,'site_a')
            self.assertEqual(result['dependents'],['site_b'])
            self.assertNotIn(item,result['reclaim'])

    def test_same_volume_work_and_restore_coexist(self):
        with TemporaryDirectory() as temp:
            p=Path(temp)
            plan=estimate(p,p,work_bytes=120,archive_bytes=30,restore_bytes=15)
            self.assertEqual(plan['workspace_needed_bytes'],165)
            with self.assertRaises(ValueError):
                estimate(p,p,work_bytes=-1,archive_bytes=0,restore_bytes=0)
