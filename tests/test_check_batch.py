import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import app_check_batch as batch
from ras_workflow.common import save,read,item


class CheckBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for target in ('ras_workflow.common.ROOT','ras_workflow.app_check_batch.ROOT'):
            p=patch(target,self.root);p.start();self.addCleanup(p.stop)
        save(self.root/'baseline.json',dict(test_only=True))
        save(self.root/'config.json',dict(test_only=True))
        self.m=dict(id='test_only',revision=2,summary=item(self.root/'baseline.json'),active_project='config.json')
        steps=[];confirmations={}
        for name in ('sensitivity','spacing'):
            folder=self.root/name
            save(folder/'source.json',dict(test_only=True))
            source=item(folder/'source.json')
            save(folder/'study.json',dict(specification=source,source_inputs=[],evidence=[self.m['summary']],cases=[]))
            save(folder/'confirmation.json',dict(test_only=True))
            confirmations[name]=item(folder/'confirmation.json')
            steps.append(dict(id=name,status='READY',study=item(folder/'study.json'),maximum_calculations=3))
        plan=dict(project_id='test_only',baseline=self.m['summary'],active_project='config.json',sources=[item(self.root/'config.json')],
                  status='REVIEW_REQUIRED',steps=steps,maximum_calculations=6)
        save(self.root/'batch'/'plan.json',plan);self.entry=item(self.root/'batch'/'plan.json')
        save(self.root/'batch'/'confirmation.json',dict(plan=self.entry,confirmed=True,studies=confirmations))
        self.active=dict(plan=self.entry,review=item(self.root/'batch'/'confirmation.json'))
        self.m['pending_check_batch']=self.entry
        self.patches=[]
        for target,kwargs in [('model',dict(side_effect=lambda key:copy.deepcopy(self.m))),
                              ('persist',dict(side_effect=self.persist)),
                              ('require_idle',dict())]:
            p=patch.object(batch.core,target,**kwargs);p.start();self.addCleanup(p.stop)

    def persist(self, model, *args, **kwargs):
        updated=copy.deepcopy(model)
        self.m.clear();self.m.update(updated)

    def test_changed_child_preview_is_not_displayed(self):
        save(self.root/'spacing'/'study.json',dict(altered=True))
        self.assertIsNone(batch.preview(self.entry))

    def test_only_adopted_applicable_active_ranges_are_selected(self):
        rows=[]
        for i in range(7):
            rows.append(dict(path=str(i),inactive=i==0,status='test',recommended_id='chosen',options=[
                dict(id='chosen',low=1,high=2,applicability_confirmed=i!=1)]))
        selected,deferred=batch.adopted_choices(dict(parameters=rows))
        self.assertEqual([x['path'] for x in selected],['2','3','4','5'])
        self.assertEqual([x['path'] for x in deferred],['0','1','6'])

    def test_missing_consent_or_changed_token_cannot_launch(self):
        for body in (dict(revision=2,confirmed=False,token=self.entry['sha256']),dict(revision=2,confirmed=True,token='old')):
            with patch.object(batch.core,'launch') as launch:
                with self.assertRaisesRegex(ValueError,'Confirm'):batch.start('test_only',body)
                launch.assert_not_called()

    def test_changed_baseline_and_case_sources_are_rejected(self):
        for kind in ('baseline','source'):
            with self.subTest(kind=kind):
                model=copy.deepcopy(self.m)
                if kind=='baseline':model['summary']={'path':'other.json'}
                else:save(self.root/'spacing'/'source.json',{'altered':True})
                with self.assertRaises(ValueError):batch.validate(model,self.entry)

    def test_native_model_is_excluded(self):
        self.m['native_review']='test'
        with self.assertRaisesRegex(ValueError,'workflow-built'):batch.validate(self.m,self.entry)

    def test_retry_cannot_replace_previous_confirmation_or_start_other_preview(self):
        self.m['active_check_batch']=self.active
        with self.assertRaisesRegex(ValueError,'already confirmed'):
            batch.start('test_only',dict(revision=2,confirmed=True,token=self.entry['sha256']))
        self.m['pending_check_batch']={'path':'other.json','sha256':'other'}
        with self.assertRaisesRegex(ValueError,'different check preview'):
            batch.start('test_only',dict(revision=2,confirmed=True,token=self.entry['sha256'],retry=True))

    def test_retry_launches_same_immutable_scope(self):
        self.m['active_check_batch']=self.active
        with patch.object(batch.core,'launch',return_value={'started':True}) as launch:
            self.assertEqual(batch.start('test_only',dict(revision=2,confirmed=True,token=self.entry['sha256'],retry=True)),{'started':True})
            launch.assert_called_once_with('test_only','check-batch')

    def test_launcher_conflict_retains_confirmation_and_can_resume(self):
        confirmations=read(self.root/'batch'/'confirmation.json')['studies']
        def confirm(model,entry):return confirmations[Path(entry['path']).parent.name]
        with patch.object(batch.app_study,'confirmation',side_effect=confirm),patch.object(batch.core,'launch',side_effect=ValueError('Another project is processing')):
            with self.assertRaisesRegex(ValueError,'Another project'):
                batch.start('test_only',dict(revision=2,confirmed=True,token=self.entry['sha256']))
        saved=copy.deepcopy(self.m['active_check_batch']['review'])
        self.assertEqual(batch.progress(self.m)['status'],'QUEUED')
        with patch.object(batch.core,'launch',return_value={'started':True}):
            batch.start('test_only',dict(revision=2,confirmed=True,token=self.entry['sha256'],retry=True))
        self.assertEqual(self.m['active_check_batch']['review'],saved)

    def execute(self,fail=None):
        self.m['active_check_batch']=self.active;order=[]
        def run(path,confirmation):
            name=Path(path).parent.name;order.append(name)
            result=dict(status='INCOMPLETE' if fail==name else 'NOT_CONVERGED' if name=='spacing' else 'COMPARISON_REQUIRES_REVIEW')
            save((self.root/path).parent/'analysis.json',result);return result
        def export(key,action):
            order.append(action)
            if fail=='delivery':raise ValueError('Test-only export interruption')
            self.m.update(latest_reports='test-only-reports',latest_delivery={'status':'READY_FOR_REVIEW'},exports_need_refresh=False)
        with patch.object(batch.study,'reviewed'),patch.object(batch.study,'run',side_effect=run),patch.object(batch.core,'regenerate',side_effect=export):
            if fail:
                with self.assertRaises(ValueError):batch.execute('test_only')
            else:batch.execute('test_only')
        return order,read(self.root/'batch'/'execution.json')

    def test_native_checks_then_export_and_open_hydraulic_qa(self):
        order,journal=self.execute()
        self.assertEqual(order,['sensitivity','spacing','delivery'])
        self.assertEqual(journal['status'],'COMPLETED_WITH_LIMITATIONS')
        self.assertEqual(journal['steps']['spacing']['assessment'],'NOT_CONVERGED')
        self.assertEqual(journal['engineering_acceptance'],'NOT_ASSESSED')
        self.assertNotIn('pending_check_batch',self.m)

    def test_incomplete_native_stage_stops_later_calculations_and_exports(self):
        order,journal=self.execute('sensitivity')
        self.assertEqual(order,['sensitivity']);self.assertEqual(journal['status'],'INCOMPLETE')
        self.assertEqual(journal['steps']['sensitivity']['status'],'INCOMPLETE')

    def test_export_failure_preserves_completed_study_evidence_for_retry(self):
        order,journal=self.execute('delivery')
        for name in ('sensitivity','spacing'):self.assertEqual(journal['steps'][name]['status'],'COMPLETED')
        self.assertEqual(journal['steps']['delivery']['status'],'INCOMPLETE')
        self.assertEqual(journal['status'],'INCOMPLETE')
        _,retry=self.execute()
        self.assertEqual(retry['status'],'COMPLETED_WITH_LIMITATIONS')
        self.assertNotIn('error',retry)
        self.assertEqual(len(retry['previous_failures']),1)
        self.assertEqual(retry['previous_failures'][0]['steps']['delivery']['status'],'INCOMPLETE')

    def test_changed_child_confirmation_blocks_execution(self):
        self.m['active_check_batch']=self.active
        save(self.root/'sensitivity'/'confirmation.json',{'changed':True})
        with patch.object(batch.study,'run') as run:
            with self.assertRaisesRegex(ValueError,'confirmation changed'):batch.execute('test_only')
            run.assert_not_called()

    def test_unavailable_spacing_is_not_presented_as_computed(self):
        plan=read(self.root/'batch'/'plan.json');plan['steps'][1].update(status='UNAVAILABLE',reason='NO_ELIGIBLE_INTERVALS')
        save(self.root/'batch'/'plan.json',plan);entry=item(self.root/'batch'/'plan.json')
        review=read(self.root/'batch'/'confirmation.json');review['plan']=entry;save(self.root/'batch'/'confirmation.json',review)
        self.active=dict(plan=entry,review=item(self.root/'batch'/'confirmation.json'))
        order,journal=self.execute()
        self.assertEqual(order,['sensitivity','delivery']);self.assertEqual(journal['steps']['spacing']['status'],'UNAVAILABLE')


if __name__=='__main__':unittest.main()
