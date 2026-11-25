"""Safety contracts for per-edition retirement on the local filesystem."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from ras_workflow import edition_storage as storage
from ras_workflow.common import ROOT, lock, save, sha


class EditionStorage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'work';self.ed=self.root/'projects/site_a'
        self.orig=self.ed/'survey/observations.csv';self.work=self.ed/'studies/run.csv'
        self.handoff=self.ed/'Handoff_selected/Complete/Reports/report.pdf'
        self.dem=self.root/'data/shared/terrain.tif'
        for path,content in [(self.orig,b'original'),(self.work,b'repeatable'),(self.handoff,b'pdf'),(self.dem,b'dem')]:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        for key in ('site_a','site_b'):
            save(self.root/'projects'/key/'app.json',dict(id=key,title=key,revision=1,dem='data/shared/terrain.tif'))

    def do(self,action,**extra):
        return storage.perform(self.root,'site_a',action,dict(confirmed=True,**extra))

    def verified(self):
        p=self.do('preview');a=self.do('archive',token=p['token'],directory=str(self.base))
        return dict(token=p['token'],archive_hash=a['sha256'])

    def test_shared_terrain_published_package_and_pin(self):
        p=self.do('preview');self.assertEqual(p['shared_bytes'],3)
        self.assertEqual(p['exclusive_bytes']+3,p['logical_bytes']);self.assertEqual(p['reclaimable_bytes'],10)
        args=self.verified();self.do('pin',pinned=True);self.assertEqual(self.do('preview')['reclaimable_bytes'],0)
        with self.assertRaisesRegex(ValueError,'Pinned'):self.do('retire',**args)
        self.do('pin',pinned=False);self.do('retire',**args)
        self.assertFalse(self.work.exists());self.assertTrue(all(p.is_file() for p in (self.dem,self.handoff,self.orig)))
        self.dem.unlink();self.do('restore',**args);self.assertEqual(self.dem.read_bytes(),b'dem')
        self.assertEqual(self.work.read_bytes(),b'repeatable');self.assertEqual(self.do('preview')['token'],args['token'])

    def test_interrupted_cleanup_resume_and_busy_lock(self):
        other=self.ed/'studies/second.csv';other.write_bytes(b'2nd');args=self.verified();unlink=Path.unlink
        with lock(self.root/'status/app/execution.lock'),self.assertRaises(RuntimeError):self.do('retire',**args)
        def fail(path,*a,**kw):
            if path==other:raise PermissionError('file open')
            return unlink(path,*a,**kw)
        with patch.object(Path,'unlink',fail),self.assertRaises(PermissionError):self.do('retire',**args)
        self.assertEqual(storage.archived(self.root)[0]['phase'],'RETIRING');self.assertFalse(self.work.exists())
        self.do('retire',**args);self.do('restore',**args);self.assertEqual(other.read_bytes(),b'2nd')

    def test_active_command_line_model_is_protected(self):
        args=self.verified()
        with lock(self.ed/'studies/project.lock'),self.assertRaises(RuntimeError):self.do('retire',**args)
        self.assertTrue(self.work.exists());self.assertEqual(storage.state(self.root,'site_a')['phase'],'ONLINE')

    def test_missing_registered_original_blocks_retirement(self):
        save(self.ed/'app.json',dict(id='site_a',title='Site',revision=1,attachments=[dict(path='projects/site_a/survey/lost.csv')]))
        p=self.do('preview');self.assertEqual(p['unverified_sources'],['projects/site_a/survey/lost.csv'])
        self.assertEqual(p['reclaimable_bytes'],0)

    def test_low_space_stale_manifest_and_changed_original(self):
        p=self.do('preview');before=sha(self.work)
        with patch('shutil.disk_usage',return_value=SimpleNamespace(free=1)),self.assertRaisesRegex(ValueError,'Insufficient'):
            self.do('archive',token=p['token'],directory=str(self.base))
        self.assertFalse(list(self.base.rglob('*.partial')));self.assertEqual(sha(self.work),before)
        args=self.verified();s=self.orig.stat();self.orig.write_bytes(b'changed!');os.utime(self.orig,ns=(s.st_atime_ns,s.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'changed'):self.do('retire',**args)
        self.assertEqual(storage.state(self.root,'site_a')['phase'],'ONLINE');self.assertEqual(sha(self.work),before)
        self.work.write_bytes(b'changed size')
        with self.assertRaisesRegex(ValueError,'Preview'):self.do('retire',**args)

    def test_dependents_hardlinks_archive_damage_and_restore_conflicts(self):
        ln=self.ed/'studies/alias';os.link(self.work,ln)
        self.assertEqual(self.do('preview')['candidate_files'],0);ln.unlink()
        foreign=self.root/'projects/site_b/ref.json';save(foreign,dict(parent='projects/site_a/studies/run.csv'))
        self.assertEqual(self.do('preview')['dependents'],['site_b']);foreign.unlink()
        args=self.verified();target=Path(storage.state(self.root,'site_a')['archive']);good=target.read_bytes()
        target.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'registered archive'):self.do('retire',**args)
        target.write_bytes(good);self.do('retire',**args);self.work.write_bytes(b'unrelated')
        with self.assertRaisesRegex(ValueError,'conflict'):self.do('restore',**args)
        self.assertEqual(self.work.read_bytes(),b'unrelated');self.work.unlink();self.do('restore',**args)
