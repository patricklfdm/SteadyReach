import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import app_next_review as next_review
from ras_workflow import app_check_batch, coverage_study, app_study, sensitivity_ranges
from ras_workflow.common import item, read, save


class NextReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        for module in ('common', 'app_next_review', 'app_check_batch'):
            p=patch('ras_workflow.'+module+'.ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.config=dict(test_only=True)
        save(self.root/'config.json',self.config);save(self.root/'summary.json',dict(test_only=True))
        save(self.root/'state.json',dict(calculation_status='COMPUTED',delivery=dict(status='READY_FOR_REVIEW')))
        self.model=dict(id='test_only',revision=2,model_type='river',summary=item(self.root/'summary.json'),
                        active_project='config.json',status='RESULTS_READY',phase='DONE',engine_state='state.json',
                        latest_delivery={'test_only':'keep'},errors=['original note'])
        self.summary=dict(configuration=self.config)
        def persist(model,*args,**kwargs):self.model.clear();self.model.update(copy.deepcopy(model))
        for name,kwargs in [('model',dict(side_effect=lambda _:copy.deepcopy(self.model))),
                            ('persist',dict(side_effect=persist)),('folder',dict(return_value=self.root))]:
            p=patch.object(next_review.core,name,**kwargs);p.start();self.addCleanup(p.stop)
        p=patch('ras_workflow.qa_review.load_summary',return_value=(None,self.summary,{}));p.start();self.addCleanup(p.stop)
        self.rows=[]
        p=patch('ras_workflow.qa_locator.collect',side_effect=lambda _:dict(rows=self.rows));p.start();self.addCleanup(p.stop)
        save(self.root/'preview.json',dict(source_inputs=[],evidence=[self.model['summary']],sources=[self.model['summary']]))
        self.preview=item(self.root/'preview.json')

    def proposal(self,changes=1):
        return dict(entry=self.preview,preview=dict(changes=[{}]*changes,unresolved=[]),
                    plan=dict(status='REVIEW_REQUIRED',maximum_calculations=9))

    def wet(self):self.rows=[dict(rs=100,left_excess_ft=.2,right_excess_ft=0)]

    def test_wet_ends_prioritize_coverage_without_solver_or_consent(self):
        self.wet()
        with patch.object(coverage_study,'prepare',return_value=self.proposal()) as prepare, \
             patch.object(app_check_batch,'prepare_model') as checks,patch.object(app_study,'start') as start:
            result=next_review.execute('test_only')
        self.assertEqual(result['action'],'coverage');self.assertEqual(result['status'],'PREVIEW_READY')
        self.assertEqual(prepare.call_args.args[1],dict(maximum_rounds=3,maximum_width_ft=2000))
        checks.assert_not_called();start.assert_not_called();self.assertFalse(result['solver_started'])
        self.assertNotIn('active_study',self.model);self.assertNotIn('run_confirmation',self.model)

    def test_dry_ends_prepare_checks_only_from_existing_builders(self):
        with patch.object(app_check_batch,'prepare_model',return_value=self.proposal()) as checks,patch.object(coverage_study,'prepare') as coverage:
            result=next_review.execute('test_only')
        self.assertEqual(result['action'],'checks');coverage.assert_not_called()
        self.assertTrue(checks.call_args.args[1]['sensitivity']);self.assertTrue(checks.call_args.args[1]['spacing'])
        self.assertEqual(result['maximum_calculations'],9)

    def test_wet_without_feasible_extension_does_not_fall_through_to_checks(self):
        self.wet()
        with patch.object(coverage_study,'prepare',return_value=self.proposal(0)),patch.object(app_check_batch,'prepare_model') as checks:
            result=next_review.execute('test_only')
        self.assertEqual(result['status'],'GEOMETRY_REVIEW_REQUIRED');checks.assert_not_called()

    def test_wet_structure_model_requires_geometry_judgment(self):
        self.wet();self.model['model_type']='culvert'
        with patch.object(coverage_study,'prepare') as prepare:
            result=next_review.execute('test_only')
        prepare.assert_not_called();self.assertEqual(result['reason'],'STRUCTURE_GEOMETRY_REVIEW')

    def test_imported_native_model_is_not_rebuilt(self):
        self.model['native_review']='test_only'
        with patch.object(app_check_batch,'prepare_model') as prepare:
            result=next_review.execute('test_only')
        prepare.assert_not_called();self.assertEqual(result['reason'],'IMPORTED_NATIVE_MODEL')

    def test_pending_user_scopes_and_completed_repair_are_preserved(self):
        for field in ('pending_study','pending_check_batch','latest_coverage'):
            with self.subTest(field=field):
                self.model[field]=self.preview
                with patch.object(coverage_study,'prepare') as coverage,patch.object(app_check_batch,'prepare_model') as checks:
                    result=next_review.execute('test_only')
                coverage.assert_not_called();checks.assert_not_called()
                self.assertEqual(self.model[field],self.preview);self.model.pop(field)
                self.assertEqual(result['status'],'UNAVAILABLE')

    def test_preparation_failure_preserves_success_and_existing_files(self):
        self.model['status']='PROCESSING';self.model['phase']='NEXT-REVIEW'
        with patch.object(app_check_batch,'prepare_model',side_effect=ValueError('test failure')):
            result=next_review.execute('test_only')
        self.assertEqual(result['status'],'PREPARATION_FAILED');self.assertEqual(result['error'],'test failure')
        self.assertEqual(self.model['status'],'RESULTS_READY');self.assertEqual(self.model['phase'],'DONE')
        self.assertEqual(self.model['errors'],['original note']);self.assertEqual(self.model['latest_delivery'],{'test_only':'keep'})

    def test_delivery_pending_status_survives_preparation(self):
        self.model['status']='PROCESSING'
        save(self.root/'state.json',dict(calculation_status='COMPUTED',delivery=dict(status='INCOMPLETE')))
        with patch.object(app_check_batch,'prepare_model',side_effect=ValueError('test')):next_review.execute('test_only')
        self.assertEqual(self.model['status'],'RESULTS_READY_MAP_PENDING')

    def test_changed_computed_configuration_blocks_preparation(self):
        save(self.root/'config.json',dict(changed=True))
        with patch.object(app_check_batch,'prepare_model') as checks:result=next_review.execute('test_only')
        self.assertEqual(result['status'],'PREPARATION_FAILED');checks.assert_not_called()

    def test_failed_engine_state_cannot_be_relabelled_as_computed(self):
        self.model['status']='PROCESSING'
        save(self.root/'state.json',dict(calculation_status='FAILED'))
        with self.assertRaisesRegex(ValueError,'completed baseline'):next_review.execute('test_only')
        self.assertNotEqual(self.model['status'],'RESULTS_READY')

    def display_record(self):
        with patch.object(app_check_batch,'prepare_model',return_value=self.proposal()):next_review.execute('test_only')
        self.model['pending_check_batch']=self.preview

    def test_preview_is_bound_to_summary_config_and_current_scope(self):
        self.display_record();self.assertEqual(next_review.current(self.model)['status'],'PREVIEW_READY')
        before=copy.deepcopy(self.model)
        for field,value in [('summary',{'path':'different'}),('pending_check_batch',{'path':'different'})]:
            self.model=copy.deepcopy(before);self.model[field]=value
            self.assertIsNone(next_review.current(self.model))
        self.model=before;save(self.root/'config.json',dict(changed=True))
        self.assertIsNone(next_review.current(self.model))

    def test_separate_confirmation_changes_message_without_rerunning(self):
        self.display_record();self.model['active_check_batch']=dict(plan=self.preview)
        self.assertEqual(next_review.current(self.model)['status'],'CONFIRMED_SEPARATELY')

    def test_queue_respects_busy_and_revision_guards(self):
        with patch.object(next_review.core,'launch') as launch,patch.object(next_review.core,'require_idle',side_effect=ValueError('busy')):
            with self.assertRaisesRegex(ValueError,'busy'):next_review.queue('test_only',dict(revision=2))
            launch.assert_not_called()
        with patch.object(next_review.core,'launch') as launch,patch.object(next_review.core,'require_idle'):
            with self.assertRaisesRegex(ValueError,'changed'):next_review.queue('test_only',dict(revision=1))
            launch.assert_not_called();next_review.queue('test_only',dict(revision=2))
            launch.assert_called_once_with('test_only','next-review')

    def test_public_prepare_endpoints_still_require_idle(self):
        for module,method in [(app_check_batch,'prepare'),(app_study,'prepare'),(sensitivity_ranges,'suggest')]:
            with self.subTest(module=module.__name__),patch.object(next_review.core,'require_idle',side_effect=ValueError('busy')):
                with self.assertRaisesRegex(ValueError,'busy'):getattr(module,method)('test_only',dict(revision=2))


if __name__=='__main__':unittest.main()
