"""Automatic independent follow-up: provenance, ownership, retry and no-solve gates."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import app_joint_review as joint, app_revision, app_autoprepare
from ras_workflow.common import item, read, save


class JointReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for module in ('common','app_core','app_joint_review','app_revision'):
            p=patch('ras_workflow.'+module+'.ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.config=dict(test_only=True)
        save(self.root/'config.json',self.config);save(self.root/'summary.json',dict(test_only=True))
        save(self.root/'task.json',dict(project_id='parent',status='RUNNING',pid=os.getpid()))
        self.parent=dict(id='parent',title='Test only',model_type='river',active_project='config.json',
                         summary=item(self.root/'summary.json'),task='task.json')
        self.child=dict(id='child',status='PROCESSING',task='task.json',
                        parent_revision=dict(summary=self.parent['summary']),values=dict(bank='retained'))
        self.created=[]
        for name,kwargs in [('model',dict(side_effect=lambda key:copy.deepcopy(self.child if key=='child' else self.parent))),
                            ('folder',dict(side_effect=lambda key:self.root/key)),
                            ('deletion_record',dict(side_effect=lambda key:self.root/key/'deleted.json')),
                            ('persist',dict(side_effect=self.persist))]:
            p=patch.object(joint.core,name,**kwargs);p.start();self.addCleanup(p.stop)
        p=patch.object(joint.params,'binding',side_effect=lambda child:child['values']);p.start();self.addCleanup(p.stop)
        p=patch('ras_workflow.qa_review.load_summary',return_value=(None,dict(configuration=self.config),{}));p.start();self.addCleanup(p.stop)
        p=patch.object(app_revision,'create_draft',side_effect=self.create);p.start();self.addCleanup(p.stop)
        p=patch.object(app_autoprepare,'execute',side_effect=self.execute);self.execute_mock=p.start();self.addCleanup(p.stop)
        for name in ('start','launch'):
            p=patch.object(joint.core,name,side_effect=AssertionError('No new worker or solver consent'));p.start();self.addCleanup(p.stop)

    def persist(self,model,*args,**kwargs):
        if model['id']=='child':self.child.clear();self.child.update(copy.deepcopy(model))

    def create(self,parent,body,preparation_task):
        self.created.append((copy.deepcopy(parent),copy.deepcopy(body),preparation_task))
        return dict(id='child')

    def execute(self,key):
        self.assertEqual(key,'child');self.assertEqual(self.child['task'],'task.json')
        with patch('ras_workflow.project_actions.process_alive',return_value=True):
            with self.assertRaisesRegex(ValueError,'task is running'):joint.core.require_idle(self.child)
        self.child.update(status='INPUTS_READY',values=dict(bank='prepared'))
        save(self.root/'preparation.json',dict(geometry_applied=True,attention={},
            geometry_proposal=dict(layouts=[dict(changes=[dict(rotation_deg=0),dict(rotation_deg=5)],unresolved=[])])))
        self.child['automatic_preparation']=item(self.root/'preparation.json')

    def test_one_independent_draft_keeps_parent_and_has_no_solver_consent(self):
        before=copy.deepcopy(self.parent)
        record=joint.prepare(self.parent,2000)
        self.assertEqual(self.parent,before);self.assertEqual(record['status'],'DRAFT_READY')
        self.assertEqual(record['changes'],2);self.assertEqual(record['rotations'],1)
        self.assertFalse(record['solver_started']);self.assertTrue(record['final_confirmation_required'])
        self.assertEqual(self.child['automatic_options'],dict(maximum_width_ft=2000))
        self.assertNotIn('task',self.child);self.assertNotIn('run_confirmation',self.child)

    def test_retry_preserves_completed_or_manually_edited_draft(self):
        first=joint.prepare(self.parent,2000)
        again=joint.prepare(self.parent,2000)
        self.assertEqual(again['entry'],first['entry']);self.assertEqual(len(self.created),1)
        self.child['values']['bank']='manual choice'
        again=joint.prepare(self.parent,2000)
        self.assertEqual(again['status'],'EDITED_REVISION');self.assertEqual(self.child['values']['bank'],'manual choice')
        self.assertEqual(self.execute_mock.call_count,1)
        save(self.root/'child_summary.json',dict(test_only='computed'));self.child['summary']=item(self.root/'child_summary.json')
        self.assertEqual(joint.current(first)['status'],'COMPUTED_REVISION')
        save(self.root/'child_summary.json',dict(changed=True))
        self.assertEqual(joint.current(first)['status'],'UNAVAILABLE')

    def test_current_revision_worker_is_reported_without_reading_mutable_inputs(self):
        record=joint.prepare(self.parent,2000);self.child['task']='task.json'
        with patch('ras_workflow.project_actions.process_alive',return_value=True),patch.object(joint.params,'binding',side_effect=AssertionError('Mutable input read')):
            self.assertEqual(joint.current(record)['status'],'REVISION_PROCESSING')

    def test_failure_preserves_partial_draft_and_does_not_repeat_automatically(self):
        self.execute_mock.side_effect=ValueError('test interrupted preparation')
        record=joint.prepare(self.parent,2000)
        self.assertEqual(record['status'],'PREPARATION_FAILED');self.assertEqual(self.child['status'],'NEEDS_ATTENTION')
        self.assertNotIn('task',self.child)
        again=joint.prepare(self.parent,2000)
        self.assertEqual(again['entry'],record['entry']);self.assertEqual(self.execute_mock.call_count,1)
        self.child.update(status='INPUTS_READY',automatic_preparation=item(self.root/'config.json'))
        self.assertEqual(joint.current(record)['status'],'EDITED_REVISION')

    def test_changed_evidence_is_not_presented_as_a_ready_draft(self):
        record=joint.prepare(self.parent,2000)
        save(self.root/'preparation.json',dict(changed=True))
        self.assertEqual(joint.current(record)['status'],'UNAVAILABLE')
        save(self.root/'summary.json',dict(changed=True))
        self.assertEqual(joint.current(record)['status'],'SOURCE_CHANGED')

    def test_deleted_draft_is_not_silently_recreated(self):
        joint.prepare(self.parent,2000)
        save(self.root/'child'/'deleted.json',dict(test_only=True))
        self.assertEqual(joint.prepare(self.parent,2000)['status'],'UNAVAILABLE')
        self.assertEqual(len(self.created),1)

    def test_invalid_scope_stops_before_creating_files(self):
        for change in (dict(model_type='culvert'),dict(native_review=True),dict(task=None)):
            with self.subTest(change=change),self.assertRaises(ValueError):joint.prepare(dict(self.parent,**change),2000)
        for width in (0,2100,float('nan')):
            with self.subTest(width=width),self.assertRaises(ValueError):joint.prepare(self.parent,width)
        save(self.root/'config.json',dict(changed=True))
        with self.assertRaisesRegex(ValueError,'configuration changed'):joint.prepare(self.parent,2000)
        self.assertEqual(self.created,[])


class WorkerOwnershipTests(unittest.TestCase):
    def test_internal_snapshot_cannot_bypass_another_live_worker(self):
        for record in (dict(project_id='other',status='RUNNING',pid=os.getpid()),
                       dict(project_id='parent',status='FINISHED',pid=os.getpid()),
                       dict(project_id='parent',status='RUNNING',pid=-1),
                       dict(project_id='parent',status='RUNNING',pid=os.getpid(),worker_pid=-1)):
            with self.subTest(record=record),patch.object(app_revision,'read',return_value=record):
                with self.assertRaisesRegex(ValueError,'current project worker'):
                    app_revision.create_draft(dict(id='parent',task='task.json'),{},preparation_task='task.json')

    def test_windows_launcher_and_actual_worker_may_have_different_pids(self):
        record=dict(project_id='parent',status='RUNNING',pid=-1,worker_pid=os.getpid())
        with patch.object(app_revision,'read',return_value=record):
            with self.assertRaisesRegex(ValueError,'native-model edits'):
                app_revision.create_draft(dict(id='parent',task='task.json',native_review=True),{},preparation_task='task.json')

    def test_public_revision_still_requires_idle_and_explicit_confirmation(self):
        parent=dict(id='parent',revision=2)
        with patch.object(app_revision.core,'model',return_value=parent),patch.object(app_revision.core,'require_idle') as idle,patch.object(app_revision,'create_draft') as create:
            for body in (dict(revision=1,confirmed=True),dict(revision=2,confirmed=False)):
                with self.assertRaises(ValueError):app_revision.create('parent',body)
            create.assert_not_called();self.assertEqual(idle.call_count,2)


if __name__=='__main__':unittest.main()
