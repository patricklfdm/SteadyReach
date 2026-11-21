import errno
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from zipfile import ZipFile

from ras_workflow import app_core,app_server,local_backup
from ras_workflow.common import ROOT,read,save


class LocalRecovery(unittest.TestCase):
    def test_pilot_blockers_preserve_legacy_clock_and_count_only_actual_assistance(self):
        from ras_workflow import pilot_session
        from ras_workflow.release_metrics import metrics
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp, patch.object(app_core,'BASE',Path(temp)):
            folder=app_core.folder('old')
            save(folder/'app.json',dict(id='old',revision=4,phase='RUN',status='NEEDS_ATTENTION'))
            clock=folder/'pilot_session.json'
            self.assertFalse(pilot_session.update('old',{})['intervals'])
            self.assertFalse(clock.exists())
            save(clock,dict(project_id='old',revision=1,developer_interventions=['2020-01-01'],open=None,intervals=[]))
            body=dict(action='blocker',page='review',topic='hydraulics',timer_revision=1)
            checkpoint=pilot_session.update('old',body)['checkpoints'][0]
            self.assertEqual((checkpoint['phase'],checkpoint['page'],checkpoint['model_revision']),('RUN','review',4))
            with self.assertRaises(ValueError):pilot_session.update('old',body)
            result=metrics(folder)
            self.assertEqual(result['developer_interventions'],1)
            self.assertEqual(result['human_acceptance'],'NOT_ASSESSED')
            self.assertIsNone(result['active_engineer_seconds'])
            marker_only=read(clock)
            marker_only['developer_interventions']=[]
            self.assertIsNone(metrics(folder,marker_only)['developer_interventions'])

    def test_restore_rejects_low_space_before_reading_payload(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp:
            parent=Path(temp);src=parent/'checkout';out=parent/'restored'
            save(src/'projects/test/app.json',dict(revision=5))
            archive=parent/'old.zip';local_backup.snapshot(src,archive)
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=1)),self.assertRaisesRegex(OSError,'uncompressed'):
                local_backup.restore(archive,out)
            self.assertFalse(out.exists())
            local_backup.restore(archive,out)
            self.assertEqual(read(out/'projects/test/app.json'),{'revision':5})

    def test_restore_only_selected_pdf_and_record_opt_in_time(self):
        from ras_workflow.common import item
        from ras_workflow.site_delivery import seal
        from ras_workflow.release_metrics import metrics
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp,patch.object(app_core,'BASE',Path(tmp)):
            key='test';project=app_core.folder(key)
            summary=project/'summary.json';save(summary,{'configuration':{'location':{'latitude':43,'longitude':-123}}})
            full=project/'Complete';minimal=project/'Minimal'
            for folder in (full,minimal):
                pdf=folder/'Graph/Exhibit_EN.pdf';pdf.parent.mkdir(parents=True);pdf.write_bytes(b'fixture PDF')
            receipt=dict(run_id='fixture',summary=item(summary),complete=seal(full),minimal=seal(minimal),mapped=True)
            m=dict(id=key,status='RESULTS_READY',revision=5,summary=item(summary),latest_delivery=receipt)
            save(project/'app.json',m)
            pdf.write_bytes(b'damaged')
            code,result=self.http('handoff-inspect',dict(id=key,revision=5))
            self.assertEqual(code,200,result);packet=result['package']
            self.assertEqual([(r['package'],r['ok']) for r in packet['pdfs']],[('complete',True),('minimal',False)])
            body=dict(id=key,revision=5,edition=packet['edition'],package='minimal',path='Graph/Exhibit_EN.pdf')
            with patch('ras_workflow.native.run_isolated',side_effect=AssertionError('unexpected HEC run')):
                code,result=self.http('handoff-repair',body)
            self.assertEqual(code,200,result);self.assertEqual(result['new_solver_calls'],0)
            self.assertEqual(pdf.read_bytes(),b'fixture PDF');self.assertEqual(read(project/'app.json'),m)
            self.assertEqual(self.http('handoff-repair',dict(body,path='../summary.json'))[0],409)
            for seq,action in enumerate(('engineer','external_wait','pause','intervention')):
                code,data=self.http('pilot-clock',dict(id=key,action=action,timer_revision=seq));self.assertEqual(code,200,data)
            stats=metrics(project);self.assertGreater(stats['active_engineer_seconds'],0);self.assertGreater(stats['external_wait_seconds'],0)
            self.assertEqual(stats['developer_interventions'],1)
    def http(self,route,body):
        s=app_server.create();t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:
            token=s.url.rstrip('/').split('/')[-1];c=http.client.HTTPConnection('127.0.0.1',s.server_port,timeout=7)
            try:
                headers={'Origin':s.origin,'X-Workflow-Token':token,'Content-Type':'application/json'}
                if body is None:
                    c.request('GET','/'+token+'/'+route,headers=headers)
                else:
                    c.request('POST','/'+token+'/'+route,body=json.dumps(body),headers=headers)
                res=c.getresponse();return res.status,json.loads(res.read())
            finally:c.close()
        finally:s.shutdown();s.server_close();t.join()

    def test_duplicate_start_survives_server_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp,patch.object(app_core,'BASE',Path(tmp)):
            key='test';folder=app_core.folder(key);task=folder/'tasks/a/task.json'
            save(task,dict(project_id=key,action='run',status='FINISHED',confirmed_review='frozen'))
            pointer=task.relative_to(ROOT).as_posix()
            save(folder/'app.json',dict(id=key,status='RESULTS_READY',revision=4,task=pointer))
            body=dict(id=key,start=True,confirmed=True,revision=4,review_token='frozen')
            with patch.object(app_core,'launch') as launch:
                for _ in range(2):
                    code,out=self.http('start',body);self.assertEqual(code,200,out);self.assertEqual(out['task'],pointer)
                launch.assert_not_called()

    def test_delivery_timeout_and_retry_use_new_task_without_solver(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp,patch.object(app_core,'BASE',Path(tmp)),patch.object(app_core,'ROOT',Path(tmp)):
            key='local';folder=app_core.folder(key);folder.mkdir()
            save(folder/'app.json',dict(id=key,status='RESULTS_READY',revision=1))
            # Production rel() is relative to the checkout. Bind the isolated
            # fixture directory to the identical path contract in this test.
            with patch.object(app_core,'rel',side_effect=lambda p:Path(p).relative_to(tmp).as_posix()),\
                    patch.object(app_core,'subprocess',SimpleNamespace(Popen=Mock(return_value=SimpleNamespace(pid=os.getpid())),DEVNULL=-3)),\
                    patch.object(app_core,'run') as solver:
                code,first=self.http('delivery',dict(id=key));self.assertEqual(code,200,first)
                with patch.object(app_core,'regenerate',side_effect=TimeoutError('QGIS export timeout')),patch('traceback.print_exc'):
                    self.assertEqual(app_core.worker(first['task']),1)
                self.assertEqual(read(Path(tmp)/first['task'])['status'],'FAILED')
                code,second=self.http('delivery',dict(id=key));self.assertEqual(code,200,second)
                with patch.object(app_core,'regenerate') as retry:
                    self.assertEqual(app_core.worker(second['task']),0);retry.assert_called_once_with(key,'delivery')
                self.assertNotEqual(first['task'],second['task']);solver.assert_not_called()

    def test_acquisition_and_native_export_interruptions_preserve_prior_result(self):
        faults=[('acquire','ras_workflow.app_acquisition.analyze',ConnectionResetError('Download interrupted')),
                ('native-export','ras_workflow.app_outputs.retry',RuntimeError('Interactive desktop unavailable'))]
        for action,target,problem in faults:
            with self.subTest(action=action),tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp,\
                    patch.object(app_core,'BASE',Path(tmp)),patch.object(app_core,'ROOT',Path(tmp)):
                key='isolated';folder=app_core.folder(key);folder.mkdir()
                proof=folder/'prior-result';proof.write_bytes(b'previous sealed fixture')
                save(folder/'app.json',dict(id=key,status='RESULTS_READY',revision=2,summary={'path':proof.name}))
                with patch.object(app_core,'rel',side_effect=lambda p:Path(p).relative_to(tmp).as_posix()),\
                        patch.object(app_core,'subprocess',SimpleNamespace(Popen=Mock(return_value=SimpleNamespace(pid=os.getpid())),DEVNULL=-3)),\
                        patch.object(app_core,'run') as solver:
                    code,first=self.http(action,dict(id=key));self.assertEqual(code,200,first)
                    with patch(target,side_effect=problem),patch('traceback.print_exc'):
                        self.assertEqual(app_core.worker(first['task']),1)
                    self.assertEqual(proof.read_bytes(),b'previous sealed fixture')
                    self.assertEqual(app_core.model(key)['summary']['path'],proof.name)
                    self.assertIn(str(problem),app_core.model(key)['errors'])
                    code,second=self.http(action,dict(id=key));self.assertEqual(code,200,second)
                    with patch(target):
                        self.assertEqual(app_core.worker(second['task']),0)
                    self.assertNotEqual(first['task'],second['task']);solver.assert_not_called()
    def test_backup_restores_sole_attachment_and_shared_terrain(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp:
            here=Path(temp);src=here/'workspace'
            for path,content in [('projects/p/source/only.pdf',b'unique original'),('data/terrain/tile.tif',b'shared raster'),
                                  ('status/app/server.json',b'session secret')]:
                f=src/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(content)
            archive=here/'snapshot.zip';local_backup.snapshot(src,archive)
            out=here/'recovered';local_backup.restore(archive,out)
            self.assertEqual((out/'projects/p/source/only.pdf').read_bytes(),b'unique original')
            self.assertEqual((out/'data/terrain/tile.tif').read_bytes(),b'shared raster')
            self.assertFalse((out/'status/app/server.json').exists())
            with self.assertRaisesRegex(ValueError,'new folder'):local_backup.restore(archive,out)
            bad=here/'bad.zip'
            with ZipFile(archive) as a,ZipFile(bad,'w') as b:
                for key in a.namelist():b.writestr(key,b'changed' if key.endswith('.pdf') else a.read(key))
            with self.assertRaisesRegex(ValueError,'fingerprint'):local_backup.restore(bad,here/'invalid')
            self.assertFalse((here/'invalid').exists())

    def test_lost_worker_publication_never_computes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp:
            p=Path(temp)/'task.json';save(p,dict(project_id='fixture',action='run',status='RUNNING',pid=10))
            with patch.object(app_core,'model',return_value={'task':'different'}),patch.object(app_core.time,'sleep'),patch.object(app_core,'run') as solver:
                self.assertEqual(app_core.worker(p),1)
            self.assertEqual(read(p)['status'],'INTERRUPTED');solver.assert_not_called()

    def test_reopening_after_real_worker_exit_recovers_the_saved_project(self):
        from ras_workflow.common import item,sha
        # Only the export payload is substituted. Web launch, Windows process exit,
        # task publication, process queries and the kernel lock all run normally.
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp:
            here=Path(tmp)
            child=here/'app.py'
            child.write_text(
                "import os,sys,time\nfrom pathlib import Path\n"
                f"sys.path.insert(0,{str(ROOT)!r})\n"
                "from ras_workflow import app_core as core\n"
                "here=Path(__file__).resolve().parent\n"
                "core.ROOT=here; core.BASE=here/'projects'\n"
                "core.rel=lambda p: Path(p).resolve().relative_to(here).as_posix()\n"
                "def export(key,action):\n"
                "    assert action=='delivery'\n"
                "    if not (here/'retry').exists():\n"
                "        (here/'entered').touch()\n"
                "        end=time.monotonic()+15\n"
                "        while not (here/'interrupt').exists() and time.monotonic()<end: time.sleep(.02)\n"
                "        os._exit(29)\n"
                "    model=core.model(key);model.update(status='RESULTS_READY');core.persist(model)\n"
                "core.regenerate=export\n"
                "raise SystemExit(core.worker(sys.argv[2]))\n",encoding='utf8')
            key='site_interrupt'
            project=here/'projects'/key
            proof=project/'summary.json';save(proof,{'fixture':'earlier successful solve'})
            ref=item(proof)
            save(project/'app.json',dict(id=key,revision=3,title='Isolated interruption',status='RESULTS_READY',summary=ref))
            def wait_for(check):
                limit=time.monotonic()+15
                while not check():
                    if time.monotonic()>=limit:self.fail('Worker failed to reach expected state')
                    time.sleep(.03)
            with patch.object(app_core,'ROOT',here),patch.object(app_core,'BASE',here/'projects'),\
                    patch.object(app_core,'rel',side_effect=lambda p:Path(p).relative_to(here).as_posix()):
                code,first=self.http('delivery',dict(id=key));self.assertEqual(code,200,first)
                wait_for((here/'entered').exists)
                self.assertEqual(self.http('state',None)[1]['projects'][0]['status'],'PROCESSING')
                (here/'interrupt').touch()
                job=here/first['task']
                wait_for(lambda:not app_core.task_alive(read(job)))
                reopened=self.http('state',None)[1]['projects'][0]
                self.assertEqual((reopened['status'],reopened['summary']),('INTERRUPTED',ref))
                (here/'retry').touch()
                code,second=self.http('delivery',dict(id=key));self.assertEqual(code,200,second)
                self.assertNotEqual(first['task'],second['task'])
                new=here/second['task']
                wait_for(lambda:read(new)['status']=='FINISHED' and not app_core.task_alive(read(new)))
                self.assertEqual(sha(proof),ref['sha256'])
                self.assertEqual(self.http('state',None)[1]['projects'][0]['status'],'RESULTS_READY')

    def test_disk_exhaustion_during_atomic_project_save_preserves_last_revision(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp,patch.object(app_core,'BASE',Path(tmp)):
            key='site_partial';project=app_core.folder(key);path=project/'app.json'
            before=dict(id=key,revision=3,status='NEW',metadata={},gis=False)
            save(path,before);original_write=Path.write_text
            def partial_write(file,content,*args,**kw):
                if file.parent==project and file.name.startswith('app.json.') and file.suffix=='.partial':
                    original_write(file,content[:10],*args,**kw)
                    raise OSError(errno.ENOSPC,'out of space')
                return original_write(file,content,*args,**kw)
            with patch.object(Path,'write_text',partial_write):
                code,data=self.http('save',dict(id=key,revision=3,gis=True))
            self.assertEqual(code,507,data);self.assertEqual(read(path),before)
            self.assertEqual(list(project.glob('*.partial')),[])
            self.assertEqual(self.http('state',None)[1]['projects'][0]['revision'],3)

    def test_open_hec_ras_blocks_the_real_worker_before_launch(self):
        from ras_workflow import worker
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as tmp:
            path=Path(tmp);project=path/'Model.prj';project.write_bytes(b'preserved fixture')
            req=path/'request.json'
            save(req,dict(project=project.relative_to(ROOT).as_posix(),run_id='isolated',case_kind='software_validation',engine={}))
            with patch('ras_workflow.native_session.ras_processes',return_value=[123]),\
                  patch.object(worker.subprocess,'Popen') as launch,patch('traceback.print_exc'):
                self.assertEqual(worker.main(req),1);launch.assert_not_called()
            receipt=read(path/'execution.json')
            self.assertEqual(receipt['blocking_code'],'USER_PROJECT_OPEN')
            self.assertFalse(receipt['solver_invoked']);self.assertEqual(project.read_bytes(),b'preserved fixture')

    def test_disk_full_is_actionable_over_normal_http(self):
        s=app_server.create();t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:
            token=s.url.rstrip('/').split('/')[-1];c=http.client.HTTPConnection('127.0.0.1',s.server_port,timeout=5)
            try:
                with patch.object(app_core,'create',side_effect=OSError(errno.ENOSPC,'out of space')):
                    c.request('POST','/'+token+'/create',body='{}',headers={'Origin':s.origin,'X-Workflow-Token':token,'Content-Type':'application/json'})
                    resp=c.getresponse();self.assertEqual(resp.status,507);self.assertIn('last saved step',json.loads(resp.read())['error'])
            finally:c.close()
        finally:s.shutdown();s.server_close();t.join()

    def test_unknown_operator_time_and_no_unrecorded_interventions(self):
        from ras_workflow.release_metrics import metrics
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp:
            here=Path(temp);r=metrics(here)
            self.assertIsNone(r['active_engineer_seconds']);self.assertIsNone(r['developer_interventions'])
            session=dict(project_id=here.name,developer_interventions=[],
                         intervals=[dict(kind='engineer',started_utc='2026-01-01T00:00:00+00:00',finished_utc='2026-01-01T00:00:04+00:00')])
            r=metrics(here,session);self.assertEqual(r['developer_interventions'],0)
            self.assertEqual(r['active_engineer_seconds'],4);self.assertIsNone(r['external_wait_seconds'])

    def test_site_rate_counts_retries_once_and_excludes_unknowns(self):
        from ras_workflow.release_metrics import cohort
        def trial(key,day,passed):
            return dict(project_id=key,attempts=[dict(attempt=key,finished='2020-01-0'+str(day)+'T12:00:00+00:00',
                                                        first_attempt_pair_registered=passed)])
        rows=[trial('failed',1,False),trial('retry',2,True),trial('passed',3,True),dict(project_id='waiting',attempts=[])]
        data=cohort({'A':['retry','failed'],'B':['passed'],'C':['waiting']},rows)
        self.assertEqual((data['eligible_sites'],data['unknown_sites'],data['first_success_rate']),(2,1,.5))
        with self.assertRaises(ValueError):cohort({'A':['retry'],'B':['retry']},rows)
