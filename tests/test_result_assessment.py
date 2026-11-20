"""Synthetic regression inputs exercise release rules; site acceptance reads real HDF files separately."""
from pathlib import Path
import tempfile
import h5py
import numpy as np
from ras_workflow import qa
from ras_workflow.common import ROOT, item, save
from unittest import TestCase
from unittest.mock import patch

from ras_workflow import result_assessment as assess


class ResultAssessmentTests(TestCase):
    def setUp(self):
        e={'path':'test','sha256':'test'}
        self.model={'summary':e}
        self.hyd=dict(model_type='river',case_kind='site_conditional',run_id='unit',flow_regime='subcritical',
                      profiles=[{'profile_id':'Q100'}],channel_geometry_basis='surveyed_channel',raw_hdf=e,raw_controller=e)
        self.summary=dict(hydraulics=self.hyd,hydraulic_results=e,gate=dict(status='READY_CONDITIONAL',input_adequacy_status='CONDITIONAL_UNVERIFIED'))
        self.diagnostics=dict(issues=[],sources=[],warning_coverage='ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH')
        change=lambda value:dict(path='boundary_slopes.downstream',before=.01,after=value)
        cases=[dict(id=k,changes=[change(v)]) for k,v in [('low',.009),('high',.011)]]
        self.study=dict(cases=cases,analysis=e,comparisons=[dict(case=c['id'],cross_section_differences=[
            dict(profile='Q100',station=s,delta_wse_ft=.02) for s in ('200','100')]) for c in cases])
        self.spacing=dict(convergence={'status':'STABLE_AT_REVIEW_THRESHOLD'},end_coverage={'status':'ENDS_ABOVE_COMPUTED_WATER'},
            intervals=[{}],cases=[dict(section_count=2),{},{}],comparisons=[])
        self.field={'events':[dict(role='holdout',residual_ft=.01,uncertainty_ft=.03,location={'rs':'200'})]}
        self.package={'status':'VERIFIED_MAPPED'}
        self.review={'status':'NO_CURRENT_SUBMISSION'}

    def assess(self,errors=()):
        with patch.object(assess,'packages',return_value=self.package),patch.object(assess,'qa_decisions',return_value=self.review), \
             patch('ras_workflow.river_review_report.collect',return_value=(self.field,[])), \
             patch.object(qa,'verified_profiles',return_value={'Q100':{'200':11.,'100':10.}}):
            return assess.assess(self.model,Path('test'),self.summary,self.diagnostics,[self.study,self.spacing],{'source_errors':errors})

    def test_highest_technical_level_never_signs_design(self):
        r=self.assess()
        self.assertEqual((r['level'],r['engineering_acceptance']),(3,'NOT_ASSESSED'))

    def test_nonfinite_native_result_is_ungradable_even_with_matching_hashes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as folder:
            folder=Path(folder)
            native=folder/'plan.hdf'
            with h5py.File(native,'w') as f:
                f['Results/Steady/Output/Geometry Info/Cross Section Attributes']=np.array([(b'100',)],dtype=[('Station','S4')])
                f[qa.BASE+'/Profile Names']=np.array([b'Q100'])
                f[qa.BASE+'/Cross Sections/Flow']=[[float('nan')]]
                f[qa.BASE+'/Cross Sections/Water Surface']=[[11.0]]
            ctrl=folder/'controller.json'
            for field in ('Flow','Water Surface'):
                with h5py.File(native,'r+') as f:
                    f[qa.BASE+'/Cross Sections/Flow'][0,0]=10
                    f[qa.BASE+'/Cross Sections/'+field][0,0]=float('nan')
                entry=item(native)
                save(ctrl,dict(hdf_sha256=entry['sha256']))
                profile=dict(profile_id='Q100',flow_cfs=10,headwater_rs='100',tailwater_rs='100',
                             metrics={'headwater_wse_ft':11.,'tailwater_wse_ft':11.})
                with self.assertRaises(ValueError):
                    qa.verified_profiles(dict(raw_hdf=entry,raw_controller=item(ctrl),profiles=[profile]))

    def test_missing_stale_native_only_and_bad_package_cap_the_result(self):
        for status in ('INCOMPLETE','STALE','VERIFIED_NATIVE_ONLY','UNVERIFIED'):
            with self.subTest(status=status):
                self.package={'status':status}
                self.assertEqual(self.assess()['level'],1)
        self.assertEqual(assess.unverified('raw mismatch')['level'],0)

    def test_incomplete_warning_source_even_when_no_messages(self):
        self.diagnostics['warning_coverage']='PARTIAL'
        self.assertEqual(self.assess()['level'],1)

    def test_ordinary_warning_and_verified_disposition(self):
        self.diagnostics['issues']=[dict(code='NATIVE_DIVIDED_FLOW',severity='WARNING',station='100')]
        self.assertEqual(self.assess()['level'],2)
        self.review={'status':'CLOSED_WITH_RECORDED_CONDITIONS'}
        self.assertEqual(self.assess()['level'],3)
        self.diagnostics['issues'][0]['code']='STRUCTURE_FLOW_IMBALANCE'
        self.assertEqual(self.assess()['level'],1)

    def test_partial_boundary_and_missing_study_evidence(self):
        self.study['comparisons'].pop()
        self.assertIn('BOUNDARY_SCOPE',[r['code'] for r in self.assess()['findings']])
        self.assertEqual(self.assess(['altered study'])['level'],1)

    def test_partial_or_duplicate_station_rows_do_not_validate_boundary_scope(self):
        rows=self.study['comparisons'][0]['cross_section_differences']
        rows.pop()
        self.assertIn('BOUNDARY_SCOPE',[f['code'] for f in self.assess()['findings']])
        rows.append(rows[0])
        self.assertIn('BOUNDARY_SCOPE',[f['code'] for f in self.assess()['findings']])

    def test_spacing_scope_and_surface_dem_are_separate_findings(self):
        self.spacing.update(intervals=[],deferred_intervals=[{}])
        self.hyd['channel_geometry_basis']='conditional_surface_dem'
        codes={r['code'] for r in self.assess()['findings']}
        self.assertEqual(codes,{'SPACING','BED_BASIS'})

    def test_boundary_and_calibration_points_do_not_count_as_holdout(self):
        self.field['events']=[dict(role='boundary',residual_ft=None),dict(role='calibration',residual_ft=.001)]
        r=self.assess()
        self.assertEqual(r['holdout_observations'],0)
        self.assertIn('FIELD_SUPPORT',[f['code'] for f in r['findings']])
        self.field['events']=[dict(role='holdout',residual_ft=3,uncertainty_ft=.03,location={'rs':'100'})]
        self.assertIn('FIELD_RESIDUAL',[f['code'] for f in self.assess()['findings']])

    def test_revision_reads_its_own_results_even_for_legacy_drafts(self):
        from ras_workflow.app_core import edition_record
        own = {'path':'projects/child/observations/own.json'}
        parent = {'path':'projects/parent/geometry_comparisons/other.json'}
        record = dict(id='child',parent_revision={'project_id':'parent'},river_observations=own,
                      observed_event_history=[parent,own],latest_geometry_comparison=parent,
                      latest_observed_event=parent,native_export_attempt={'receipt':parent})
        cleaned = edition_record(record)
        self.assertEqual(cleaned['observed_event_history'],[own])
        self.assertEqual(cleaned['river_observations'],own)
        for field in ('latest_geometry_comparison','latest_observed_event','native_export_attempt'):
            self.assertNotIn(field,cleaned)
        self.assertEqual(edition_record({'id':'parent','latest_geometry_comparison':parent})['latest_geometry_comparison'],parent)

    def test_changed_assessment_cannot_be_exported_as_displayed(self):
        with patch('ras_workflow.result_guidance.collect',return_value={'assessment':{'evidence_hash':'changed'}}):
            with self.assertRaisesRegex(ValueError,'Assessment changed'):
                assess.save_summary('unit',{'language':'zh','assessment_hash':'previous'})

    def test_reports_without_binding_cannot_cover_an_attached_study(self):
        self.assertEqual(assess.packages({'latest_study':{'path':'study.json'}},None,None)['status'],'STALE')

    def test_stale_flag_skips_disk_and_foreign_case_stays_internal(self):
        self.assertEqual(assess.packages({'exports_need_refresh':True},None,None)['status'],'STALE')
        self.hyd['case_kind']='software_validation'
        self.assertEqual(self.assess()['level'],1)
