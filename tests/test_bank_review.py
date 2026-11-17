import copy
import unittest
from unittest.mock import patch

from ras_workflow import bank_review,bank_reach
from test_bank_reach import geometry,local
from test_section_spacing import fixture
from ras_workflow.section_spacing import refine,intervals,confirm_geometry
from ras_workflow.geometry_qa import review_errors,section_fingerprint


class BankReviewTests(unittest.TestCase):
    def make(self):
        g=geometry()
        for row in g['cross_sections']:
            row['bank_stations_ft']=[20.,80.]
            row['bank_candidates']=local()
        return g

    def test_current_inventory_is_readonly_and_uses_current_station_identity(self):
        g=self.make();before=copy.deepcopy(g)
        r=bank_review.inventory(g)
        self.assertEqual(g,before)
        self.assertEqual([(v['index'],v['rs']) for v in r['sections']],[(0,300.),(1,200.),(2,100.)])
        self.assertEqual(r['attention_count'],0)

    def test_legacy_spacing_rows_are_flagged_without_candidate_metadata(self):
        g=self.make();row=g['cross_sections'][1];row.pop('bank_candidates')
        row['spacing_assumptions']={'bank_basis':'Mean adjacent bank fractions'}
        r=bank_review.inventory(g)['sections'][1]
        self.assertEqual(r['confidence'],'LOW')
        self.assertEqual(r['categories'],['inferred'])
        self.assertEqual(r['evidence_class'],'assumed')

    def test_missing_metadata_is_not_silently_confident(self):
        g=self.make();g['cross_sections'][0].pop('bank_candidates')
        r=bank_review.inventory(g)
        self.assertIn('BANK_METHOD_NOT_RECORDED',r['sections'][0]['reasons'])

    def test_saved_controls_rebind_summary_without_changing_any_row(self):
        g=self.make();g['bank_reach_summary']={'input_hash':'old-32-section-context','locked_indices':[0]}
        before=copy.deepcopy(g['cross_sections'])
        self.assertEqual(bank_review.inventory(g)['reach_summary_status'],'STALE')
        bank_reach.refresh(g)
        self.assertEqual(g['cross_sections'],before)
        self.assertEqual(g['bank_reach_summary']['section_count'],3)
        self.assertEqual(g['bank_reach_summary']['locked_indices'],[0,1,2])
        self.assertEqual(bank_review.inventory(g)['reach_summary_status'],'CURRENT')
        after=copy.deepcopy(g);bank_reach.refresh(g);self.assertEqual(g,after)

    def test_same_count_but_reordered_or_moved_sections_invalidates_summary(self):
        for change in ('order','coordinates'):
            g=self.make();bank_reach.refresh(g)
            if change=='order':g['cross_sections'].reverse()
            else:g['cross_sections'][0]['center_xy'][0]+=1
            self.assertEqual(bank_review.inventory(g)['reach_summary_status'],'STALE')

    def test_invalid_banks_are_first_and_saved_banks_stay_unchanged(self):
        g=self.make();g['cross_sections'][2]['bank_stations_ft']=[90.,10.]
        r=bank_review.inventory(g)
        self.assertEqual(r['priority_indices'][0],2)
        self.assertEqual(g['cross_sections'][2]['bank_stations_ft'],[90.,10.])

    def test_profile_changes_invalidate_recorded_bank_derivation(self):
        g=self.make();row=g['cross_sections'][0]
        row['bank_candidates']=bank_review.spacing_metadata(row,[400.,200.])
        row['elevation_ft'][50]-=1
        self.assertIn('STALE_BANK_PROFILE_CONTEXT',bank_review.inventory(g)['sections'][0]['reasons'])

    def test_new_refined_sections_have_bound_assumptions_and_can_be_confirmed(self):
        g,sampler=fixture();g['bank_reach_summary']={'input_hash':'old','locked_indices':[]}
        before=copy.deepcopy(g)
        result,added,_=refine(g,intervals(g,[],'all'),sampler)
        self.assertEqual(g,before)
        rows={r['rs']:r for r in result['cross_sections']}
        for change in added:
            row=rows[change['station']];method=row['bank_candidates']
            self.assertEqual(method['confidence'],'LOW')
            self.assertEqual(method['evidence_class'],'assumed')
            self.assertEqual(method['profile_context'],bank_review.profile_context(row))
            self.assertEqual(method['bracket'],change['bracket'])
            self.assertEqual([row['station_ft'][i] for i in method['selected_indices']],row['bank_stations_ft'])
        self.assertEqual(result['bank_reach_summary']['section_count'],7)
        self.assertFalse(review_errors(confirm_geometry(result,{'test_only':True})))

    def test_non_sample_bank_values_remain_valid_model_inputs(self):
        g=self.make();g['cross_sections'][0]['bank_stations_ft']=[20.25,79.75]
        self.assertTrue(bank_review.inventory(g)['sections'][0]['valid_pair'])

    def test_current_explicit_bank_choice_is_not_relabelled_as_interpolation(self):
        g=self.make();row=g['cross_sections'][0]
        row['spacing_assumptions']={'bank_basis':'Mean adjacent bank fractions'}
        row['terrain_review']={'identity':'LOCAL_SELECTION_NO_ENGINEERING_REVIEW','fingerprint':section_fingerprint(row)}
        r=bank_review.inventory(g)['sections'][0]
        self.assertEqual(r['confidence'],'USER_SELECTED')
        self.assertFalse(r['needs_attention'])
        from ras_workflow.app_parameters import attention
        with patch('ras_workflow.app_acquisition.snapshot', return_value={'documents':[]}):
            notices=attention({},[{'key':r['field'],'bank_review':r,'answer':{'candidate_record':{'bank_method':{'confidence':'LOW'}}}}])
        self.assertFalse(notices)
        row['elevation_ft'][50]-=1
        self.assertTrue(bank_review.inventory(g)['sections'][0]['needs_attention'])


if __name__=='__main__':unittest.main()
