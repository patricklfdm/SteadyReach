"""Synthetic selector contracts, kept separate from real site run evidence."""
import copy
import unittest
from unittest.mock import patch
from tests.test_section_spacing import fixture
from ras_workflow.spacing_selection import recommend, eligible, limit_candidates
from ras_workflow.section_spacing import SPACING_CODES


def data():
    geometry,_=fixture()
    rows=[dict(profile='Q100',river='R',reach='Main',rs=str(s['rs']),station_ft=s['station_ft'],
        elevation_ft=s['elevation_ft'],banks_ft=s['bank_stations_ft'],egl_ft=7.,wse_ft=6.,froude=.5)
        for s in geometry['cross_sections']]
    return geometry,rows


class SelectionTests(unittest.TestCase):
    def test_project_without_bank_replacement_needs_no_optional_record(self):
        from ras_workflow.bank_reassessment import selection_sources
        self.assertEqual(selection_sources({}),[])
        self.assertEqual(selection_sources({'provenance':['Published survey citation',{'role':'terrain'}]}),[])

    def test_empty_feasibility_preview_cannot_start_solver(self):
        from ras_workflow import app_study
        m=dict(revision=1,pending_study=dict(path='preview.json',sha256='token'),summary=dict(path='baseline'))
        plan=dict(analysis_kind='section_spacing',status='NO_ELIGIBLE_INTERVALS',cases=[],evidence=[m['summary']])
        with patch.object(app_study.core,'model',return_value=m),patch.object(app_study.core,'require_idle'), \
             patch.object(app_study,'intact',return_value=True),patch.object(app_study,'read',return_value=plan), \
             patch.object(app_study.core,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'No complete nested'):
                app_study.start('test',dict(revision=1,confirmed=True,token='token'))
            launch.assert_not_called()

    def test_observations_select_without_warnings_and_preserve_input(self):
        g,rows=data();rows[0].update(egl_ft=9.,wse_ft=6.);original=copy.deepcopy((g,rows))
        candidates,policy=recommend(g,[],rows,SPACING_CODES)
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['observations'][0]['velocity_head_change_ft'],2.)
        self.assertEqual(candidates[0]['priority_tier'],1)
        self.assertEqual((g,rows),original)
        self.assertIn('not a proof',policy['limitation'])

    def test_difficulty_precedes_advisory_without_count_inflation(self):
        g,rows=data()
        warnings=[dict(id=str(i),profile='Q100',station='400',code='NATIVE_LARGE_ENERGY_LOSS') for i in range(9)]
        warnings.append(dict(id='critical',profile='Q100',station='100',code='NATIVE_CRITICAL_DEPTH_FALLBACK'))
        chosen,_=recommend(g,warnings,rows,SPACING_CODES)
        self.assertEqual(chosen[0]['upstream_rs'],200)
        self.assertEqual(chosen[0]['priority_tier'],3)

    def test_other_reach_profile_and_unlocated_messages_remain_visible(self):
        g,rows=data()
        warnings=[dict(id='wrong-reach',profile='Q100',station='300',code='NATIVE_LARGE_ENERGY_LOSS',evidence=dict(reach='Elsewhere')),
                  dict(id='wrong-profile',profile='Q500',station='300',code='NATIVE_LARGE_ENERGY_LOSS'),
                  dict(id='global',profile='Q100',station=None,code='NATIVE_LARGE_ENERGY_LOSS')]
        chosen,policy=recommend(g,warnings,rows,SPACING_CODES)
        self.assertEqual(chosen,[]);self.assertEqual(len(policy['unlocated_spacing_issues']),3)

    def test_profiles_never_form_cross_profile_intervals(self):
        g,rows=data();other=copy.deepcopy(rows)
        for r in other:r.update(profile='Q500',egl_ft=70.,wse_ft=60.)
        chosen,_=recommend(g,[],rows+other,SPACING_CODES)
        self.assertEqual(chosen,[])

    def test_missing_head_is_unknown_and_channel_froude_is_explicit(self):
        g,rows=data();rows[0].update(egl_ft=None,froude=1.2)
        chosen,_=recommend(g,[],rows,SPACING_CODES)
        observation=chosen[0]['observations'][0]
        self.assertIsNone(observation['energy_loss_ft']);self.assertIsNone(observation['velocity_head_change_ft'])
        self.assertEqual(observation['triggers'],['CHANNEL_FROUDE_TRANSITION'])

    def test_negative_native_head_is_not_used_as_velocity(self):
        g,rows=data();rows[0]['wse_ft']=9.
        chosen,_=recommend(g,[],rows,SPACING_CODES)
        self.assertEqual(chosen,[])

    def test_changed_sample_bank_and_identity_rejected(self):
        for field in ('rs','station_ft','banks_ft'):
            g,rows=data();rows=copy.deepcopy(rows)
            if field=='rs':rows[0][field]='401'
            else:rows[0][field][0]+=1
            with self.assertRaisesRegex(ValueError,'differ'):recommend(g,[],rows,SPACING_CODES)

    def test_exact_warning_threshold_does_not_trigger(self):
        g,rows=data();rows[0].update(egl_ft=8.,wse_ft=6.5)
        chosen,_=recommend(g,[],rows,SPACING_CODES)
        self.assertEqual(chosen,[])

    def test_unavailable_interval_does_not_discard_remaining_candidates(self):
        g,rows=data();rows[1]['froude']=1.2
        choices,_=recommend(g,[],rows,SPACING_CODES)
        g['cross_sections'][0]['ineffective_left']=[10,8]
        accepted,excluded=eligible(g,choices,1.)
        self.assertEqual(len(accepted),1);self.assertEqual(len(excluded),1)
        self.assertEqual(excluded[0]['reason_code'],'SECTION_SPECIFIC_CONTROLS')
        accepted,excluded=eligible(g,choices,20.)
        self.assertFalse(accepted);self.assertEqual(len(excluded),2)

    def test_budget_deferred_explicit_and_bad_limits_rejected(self):
        g,rows=data();rows[1]['froude']=1.2
        choices,_=recommend(g,[],rows,SPACING_CODES)
        accepted,deferred=limit_candidates(g,choices,1)
        self.assertEqual(len(accepted),1);self.assertEqual(len(deferred),1)
        self.assertEqual(deferred[0]['reason_code'],'CONFIRMED_SEARCH_LIMIT')
        for bad in (True,0,101,2.5,None):
            with self.assertRaises(ValueError):limit_candidates(g,choices,bad)

    def test_native_section_cap_accounts_for_both_nested_levels(self):
        g,rows=data();rows[1]['froude']=1.2
        choices,_=recommend(g,[],rows,SPACING_CODES)
        g['cross_sections']*=124
        accepted,deferred=limit_candidates(g,choices,12)
        self.assertEqual(len(accepted),1);self.assertEqual(deferred[0]['reason_code'],'SECTION_COUNT_LIMIT')


if __name__=='__main__':unittest.main()
