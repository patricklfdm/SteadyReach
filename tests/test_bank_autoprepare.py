import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import bank_autoprepare as auto, bank_reassessment as banks
from ras_workflow.common import read, save, intact
from ras_workflow.geometry_qa import section_fingerprint
import test_bank_reassessment


class AutomaticBankTests(unittest.TestCase):
    def fixture(self, low=False):
        g,d,p=test_bank_reassessment.BankReassessmentTests().fixture(low)
        proposals=[dict(p['rows'][0]['method']) for _ in g['cross_sections']]
        return g,d,proposals

    def prepare(self,g,d,proposals,preserved=()):
        with patch('ras_workflow.bank_reach.propose_reach',return_value=(proposals,{})):
            return auto.prepare(g,d,preserved)

    def test_stable_inherited_pair_staged_without_consent_or_original_mutation(self):
        g,d,proposals=self.fixture();before=copy.deepcopy((g,d))
        p,selected,updated=self.prepare(g,d,proposals)
        self.assertEqual(selected,[1]);self.assertEqual((g,d),before)
        self.assertFalse(updated['consent'])
        answer=updated['answers']['g.cross_sections.1.bank_stations_ft']
        self.assertEqual(answer['value'],[20.,80.]);self.assertEqual(answer['evidence_class'],'inferred')
        self.assertTrue(answer['automatic_bank_preparation']);self.assertFalse(answer['confirmed'])
        self.assertNotIn('automatic_preparation',answer)
        self.assertNotIn('terrain_review',updated['geometry']['cross_sections'][1])
        self.assertEqual(updated['geometry']['cross_sections'][0],g['cross_sections'][0])
        self.assertEqual(updated['geometry']['cross_sections'][2],g['cross_sections'][2])

    def test_ambiguous_candidates_remain_unmodified(self):
        g,d,proposals=self.fixture(low=True)
        p,selected,updated=self.prepare(g,d,proposals)
        self.assertEqual(p['candidate_count'],1);self.assertEqual(selected,[]);self.assertIsNone(updated)

    def test_manual_values_even_invalid_ones_are_not_replaced(self):
        for value in ([25.,75.],[None,75.]):
            g,d,proposals=self.fixture();g['cross_sections'][1]['bank_stations_ft']=value
            d['answers']['g.cross_sections.1.bank_stations_ft']=dict(value=value,evidence_class='assumed')
            p,selected,updated=self.prepare(g,d,proposals)
            self.assertEqual(selected,[]);self.assertIsNone(updated)
            self.assertEqual(p['excluded'][0]['reason'],'SAVED_BANK_CONTROL')

    def test_new_spacing_marker_allows_staging_but_manual_edit_revokes_it(self):
        g,d,proposals=self.fixture()
        d['answers']['g.cross_sections.1.bank_stations_ft']=dict(value=[25.,75.],inherited_spacing_bank=True,source_case={})
        self.assertEqual(self.prepare(g,d,proposals)[1],[1])
        d['answers']['g.cross_sections.1.bank_stations_ft']=dict(value=[25.,75.],basis='Manual edit')
        self.assertEqual(self.prepare(g,d,proposals)[1],[])

    def test_manual_control_survives_later_geometry_metadata_removal(self):
        g,d,proposals=self.fixture();row=g['cross_sections'][1]
        row['terrain_review']=dict(identity='LOCAL_SELECTION_NO_ENGINEERING_REVIEW',fingerprint=section_fingerprint(row))
        preserved=auto.protected(g,d['answers']);row.pop('terrain_review')
        self.assertEqual(self.prepare(g,d,proposals,preserved)[1],[])

    def test_repeat_preparation_does_not_accumulate_changes(self):
        g,d,proposals=self.fixture();_,_,updated=self.prepare(g,d,proposals)
        before=copy.deepcopy(updated)
        self.assertEqual(self.prepare(updated['geometry'],updated,proposals)[1],[])
        self.assertEqual(updated,before)

    def test_spatial_structure_and_roughness_exclusions_still_apply(self):
        for kind in ('spatial','structure','roughness'):
            g,d,proposals=self.fixture()
            if kind=='spatial':g['cross_sections'][1]['cutline_xy']=g['cross_sections'][0]['cutline_xy']
            elif kind=='structure':g['structure']={'us_xs_rs':200.}
            else:g['cross_sections'][1]['manning_segments']=[{'test_only':True}]
            self.assertEqual(self.prepare(g,d,proposals)[1],[])

    def test_persistence_preserves_source_evidence_and_invalidates_prior_run_consent(self):
        g,d,proposals=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sp=root/'session.json';save(root/'draft.json',d)
            m=dict(id='test_only',session='session.json',revision=2,pending_review={},run_confirmation={})
            with patch.object(auto,'ROOT',root),patch('ras_workflow.common.ROOT',root),\
                 patch('ras_workflow.intake._load',return_value=(sp,{}, {},d)),\
                 patch('ras_workflow.intake._objects',return_value=({},g)),\
                 patch('ras_workflow.bank_reach.propose_reach',return_value=(proposals,{})),\
                 patch('ras_workflow.app_core.persist'):
                result=auto.stage(m)
                updated=read(root/'draft.json');sources=updated['geometry_edit_sources']
                self.assertTrue(intact(sources));self.assertEqual(sources[0]['role'],'bank_reassessment')
                receipt=read(root/sources[0]['path'])
                self.assertEqual(receipt['proposal']['selection_mode'],'AUTOMATIC_EDITABLE_DRAFT')
                self.assertTrue(receipt['final_confirmation_required']);self.assertEqual(result['staged_count'],1)
            self.assertNotIn('run_confirmation',m);self.assertNotIn('pending_review',m)
            self.assertEqual(m['revision'],3)

    def test_completed_or_native_project_cannot_stage(self):
        for key in ('active_project','native_review'):
            with self.assertRaisesRegex(ValueError,'editable revision'):auto.stage({key:'test'})

    def test_final_review_explicitly_lists_staged_banks(self):
        from ras_workflow.app_parameters import attention
        with patch('ras_workflow.app_acquisition.snapshot',return_value={'documents':[]}):
            result=attention({},[dict(key='g.cross_sections.1.bank_stations_ft',answer={'automatic_bank_preparation':True})])
        self.assertEqual(result[0]['code'],'AUTOMATIC_BANK_DRAFT')
        self.assertEqual(result[0]['fields'],['g.cross_sections.1.bank_stations_ft'])


if __name__=='__main__':unittest.main()
