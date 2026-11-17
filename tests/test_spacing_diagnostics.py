"""Synthetic comparison contracts; native acceptance is run separately."""
import copy
import unittest
from unittest.mock import patch
from ras_workflow import spacing_diagnostics as review


def row(rs,wse,profile='Q100',**kw):
    return dict(profile=profile,river='R',reach='A',rs=str(rs),wse_ft=wse,egl_ft=wse,
                left_excess_ft=0,right_excess_ft=0,froude=.6,issues=[],**kw)


class SpacingDiagnosticsTests(unittest.TestCase):
    def fixture(self):
        return [[row(300,12),row(200,11),row(100,10)],
                [row(300,12.02),row(250,11.5),row(200,11.5),row(100,10)],
                [row(300,12.03),row(275,11.7),row(250,11.8),row(200,11.6),row(100,10)]]

    def assemble(self,series):return review.assemble(['base','first','second'],series,.1)

    def test_pairs_use_all_retained_rows_not_only_original_stations(self):
        series=self.fixture();original=copy.deepcopy(series);result=self.assemble(series)
        self.assertEqual(series,original)
        self.assertEqual(result['pairs'][0]['worst_stations'],['200'])
        self.assertEqual(result['pairs'][1]['worst_stations'],['250'])
        self.assertAlmostEqual(result['pairs'][1]['max_abs_delta_ft'],.3)
        self.assertEqual([p['matched_sections'] for p in result['pairs']],[3,4])
        added=next(r for r in result['rows'] if r['rs']=='275')
        self.assertEqual(added['origin'],'SECOND_REFINEMENT');self.assertEqual(added['delta_wse_ft'],[None,None])
        self.assertEqual(result['rows'][0]['rs'],'200')
        self.assertFalse(result['solver_started']);self.assertFalse(result['geometry_changed'])
        self.assertEqual(result['warnings_resolved'],0)

    def test_multiple_profiles_do_not_cross_match(self):
        a=self.fixture();b=copy.deepcopy(a)
        for level in b:
            for r in level:r.update(profile='Q500',wse_ft=r['wse_ft']+5)
        result=self.assemble([x+y for x,y in zip(a,b)])
        self.assertEqual(len(result['pairs']),4);self.assertEqual(result['section_profiles'],10)
        self.assertEqual({r['profile'] for r in result['rows']},{'Q100','Q500'})

    def test_missing_value_is_not_zero_or_passed(self):
        series=self.fixture();series[1][0]['wse_ft']=None
        result=self.assemble(series);r=next(r for r in result['rows'] if r['rs']=='300')
        self.assertEqual(r['delta_wse_ft'],[None,None]);self.assertEqual(r['missing_result_pairs'],[1,2])
        self.assertEqual([p['missing_results'] for p in result['pairs']],[1,1])
        self.assertEqual(result['rows'][0]['rs'],'300')

    def test_wet_and_froude_observations_do_not_close_qa(self):
        series=self.fixture();series[2][3].update(froude=1.2,right_excess_ft=.2,issues=[{'code':'NATIVE_CRITICAL_DEPTH_FALLBACK'}])
        result=self.assemble(series);r=next(r for r in result['rows'] if r['rs']=='200')
        self.assertEqual(r['wet_cases'],['second']);self.assertEqual(r['channel_froude_crossings'],[2])
        self.assertIn('NATIVE_OR_NUMERICAL_DIAGNOSTIC',r['flags'])
        self.assertEqual(result['engineering_acceptance'],'NOT_ASSESSED')

    def test_missing_section_duplicate_and_new_profile_rejected(self):
        for change in ('remove','repeat','profile'):
            s=self.fixture()
            if change=='remove':s[2].pop()
            elif change=='repeat':s[1].append(copy.deepcopy(s[1][0]))
            else:s[2].append(row(50,4,'NEW'))
            with self.subTest(change=change),self.assertRaises(ValueError):self.assemble(s)

    def test_signed_differences_and_tied_maxima_retained(self):
        s=self.fixture();s[1][0]['wse_ft']=11.5
        result=self.assemble(s)
        self.assertEqual(set(result['pairs'][0]['worst_stations']),{'200','300'})
        self.assertEqual(next(r for r in result['rows'] if r['rs']=='300')['delta_wse_ft'][0],-.5)

    def test_stale_token_rejects_before_native_work(self):
        model=dict(summary={'sha256':'baseline'},latest_spacing={'sha256':'new'})
        with patch('ras_workflow.app_core.model',return_value=model),patch('ras_workflow.app_core.require_idle'),patch('ras_workflow.spacing_cycle.round_evidence') as native:
            with self.assertRaisesRegex(ValueError,'changed'):
                review.collect('x',dict(summary_hash='baseline',study_token='old'))
            native.assert_not_called()

    def test_old_coverage_metadata_is_derived_without_changing_saved_analysis(self):
        analysis=dict(study={'path':'study'},review={'path':'review'},cases=[dict(id='base',status='COMPUTED',summary={'path':'summary'},wet_sections=['100','100.00'])])
        original=copy.deepcopy(analysis)
        actual=dict(wet_sections=['100.0'],wet_section_profiles=[],retained_wet_sections=['100.0'],added_wet_sections=[])
        plan={'cases':[{'geometry':{'path':'geometry'}}]}
        with patch('ras_workflow.study.reviewed',return_value=(None,plan,None,None)),patch.object(review,'read',side_effect=[{'cross_sections':[{'rs':100}]},{'hydraulics':{}}]),patch.object(review,'intact',return_value=True),patch('ras_workflow.spacing_coverage.observations',return_value=actual):
            result=review.restore_legacy_coverage(analysis)
        self.assertEqual(analysis,original)
        self.assertEqual(result['end_coverage']['status'],'PROVISIONAL_WET_SECTION_ENDS')
        self.assertEqual(result['cases'][0]['wet_sections'],['100.0'])

    def test_legacy_saved_dry_claim_conflicting_with_native_wet_is_rejected(self):
        analysis=dict(study={'path':'study'},review={'path':'review'},cases=[dict(id='base',status='COMPUTED',summary={'path':'summary'},wet_sections=[])])
        plan={'cases':[{'geometry':{'path':'geometry'}}]}
        with patch('ras_workflow.study.reviewed',return_value=(None,plan,None,None)),patch.object(review,'read',side_effect=[{'cross_sections':[{'rs':100}]},{'hydraulics':{}}]),patch.object(review,'intact',return_value=True),patch('ras_workflow.spacing_coverage.observations',return_value={'wet_sections':['100.0']}):
            with self.assertRaisesRegex(ValueError,'differ from native'):review.restore_legacy_coverage(analysis)


if __name__=='__main__':unittest.main()
