import copy
import unittest
from unittest.mock import patch

from ras_workflow import result_guidance as guide


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.model = dict(model_type='river', latest_delivery={'status':'READY_FOR_REVIEW'})
        self.summary = {'hydraulics': {'run_id':'real-input-identity'}}
        self.diagnostics = dict(issues=[], warning_coverage='ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH')

    def issue(self, code, station='100'):
        self.diagnostics['issues'].append(dict(id=str(len(self.diagnostics['issues'])), code=code,
            profile='Q100', station=station, severity='WARNING', review_status='OPEN'))

    def run_plan(self, studies=(), errors=()):
        return guide.organize(self.model,self.summary,self.diagnostics,studies,errors)

    def action(self, plan, key):
        return next(v for v in plan['actions'] if v['id']==key)

    def test_complete_warning_export_does_not_recommend_reexport(self):
        self.assertNotIn('native',[v['id'] for v in self.run_plan()['actions']])

    def test_missing_scope_requires_native_evidence_even_without_numeric_issues(self):
        self.diagnostics['warning_coverage']='PARTIAL'
        self.assertEqual(self.run_plan()['actions'][0]['id'],'native')

    def test_native_and_numeric_wet_records_are_retained_but_no_qa_closed(self):
        self.issue('WET_SECTION_EDGE');self.issue('NATIVE_WET_SECTION_EDGE')
        before=copy.deepcopy(self.diagnostics);result=self.run_plan()
        self.assertEqual(self.action(result,'coverage')['records'],2)
        self.assertEqual(result['assigned_issue_count'],2)
        self.assertEqual(self.diagnostics,before)
        self.assertEqual(result['warnings_resolved'],0)
        self.assertFalse(result['solver_started']);self.assertFalse(result['geometry_changed'])

    def test_completed_repair_does_not_clear_baseline_or_repeat_batch(self):
        self.issue('WET_SECTION_EDGE')
        result=self.run_plan([{'coverage':{'status':'COVERAGE_CRITERION_MET'}}])
        self.assertEqual(self.action(result,'coverage')['mode'],'REVIEW_COMPLETED_BATCH')
        self.assertEqual(result['issue_count'],1)

    def test_all_unrecognized_messages_stay_in_review_queue(self):
        self.issue('SOME_FUTURE_CODE');self.issue('UNRECOGNIZED_STANDARD_STEP_CODE')
        result=self.run_plan()
        self.assertEqual(self.action(result,'other')['records'],2)
        self.assertEqual(result['assigned_issue_count'],result['issue_count'])

    def test_failed_evidence_does_not_suppress_work(self):
        self.issue('WET_SECTION_EDGE');result=self.run_plan(errors=['Changed source hash'])
        self.assertEqual(result['actions'][0]['id'],'evidence')
        self.assertEqual(self.action(result,'coverage')['mode'],'PREVIEW_THEN_CONFIRM')

    def test_small_sensitivity_response_keeps_boundary_judgment(self):
        study=dict(analysis={'sha256':'test'},cases=[{'id':'low','changes':[{'path':'boundary_slopes.downstream'}]}],
            comparisons=[{'case':'low','rows':[{'max_matched_xs_delta_wse_ft':0.0}]}])
        row=self.action(self.run_plan([study]),'boundary')
        self.assertEqual(row['mode'],'REVIEW_TESTED_RANGE')
        self.assertEqual(row['tested'][0]['max_delta_ft'],0)
        self.assertIn('does not establish',row['explanation']['en'])

    def test_full_stable_spacing_not_qa_pass_and_exclusions_retained(self):
        study=dict(convergence={'status':'STABLE_AT_REVIEW_THRESHOLD'},excluded_intervals=[{'upstream_rs':200,'downstream_rs':100}])
        result=self.run_plan([study]);row=self.action(result,'spacing')
        self.assertEqual(row['excluded_intervals'],study['excluded_intervals'])
        self.assertEqual(result['engineering_acceptance'],'NOT_ASSESSED')

    def test_native_import_and_culvert_do_not_offer_river_batch(self):
        self.model.update(native_review={'imported':True},model_type='culvert')
        self.issue('WET_SECTION_EDGE');self.issue('CRITICAL_DEPTH_FALLBACK')
        result=self.run_plan()
        self.assertNotIn('boundary',[v['id'] for v in result['actions']])
        self.assertEqual(self.action(result,'coverage')['mode'],'NATIVE_EDITOR')
        self.assertEqual(self.action(result,'spacing')['target'],'revision')

    def test_every_category_retains_an_issue_location(self):
        for code in guide.WET|guide.NATIVE_GAPS|guide.SPACING|guide.PATHS|guide.BALANCE:
            self.issue(code)
        result=self.run_plan()
        self.assertEqual(result['assigned_issue_count'],len(self.diagnostics['issues']))
        self.assertTrue(all(row['locations'] for row in result['actions'] if row['records']))

    def test_failed_delivery_does_not_request_resolve(self):
        self.model['latest_delivery']={'status':'INCOMPLETE','error':'network'}
        row=self.action(self.run_plan(),'delivery')
        self.assertEqual(row['mode'],'AUTOMATED_EXPORT')
        self.assertIn('without solving',row['explanation']['en'])

    def test_changed_displayed_summary_rejects_before_study_read(self):
        with patch('ras_workflow.app_core.model',return_value={'summary':{'sha256':'new'}}), \
             patch('ras_workflow.app_core.require_idle'), \
             patch('ras_workflow.report_studies.collect') as studies:
            with self.assertRaisesRegex(ValueError,'displayed calculation changed'):
                guide.collect('test',{'summary_hash':'old'})
            studies.assert_not_called()


if __name__=='__main__':unittest.main()
