import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import bank_reassessment as br, bank_review
from ras_workflow.common import save,read,intact
from test_bank_reach import geometry, local


class BankReassessmentTests(unittest.TestCase):
    def fixture(self,low=False):
        g=geometry()
        for row in g['cross_sections']:
            row['bank_stations_ft']=[25.,75.]
            row['bank_candidates']=local()
        row=g['cross_sections'][1];row['spacing_assumptions']={'bank_basis':'Adjacent bank fractions'}
        d={'revision':4,'answers':{},'geometry':copy.deepcopy(g),'consent':True}
        proposals=[dict(local(),evidence_class='inferred',method='terrain_test',basis='Synthetic terrain test') for _ in range(3)]
        if low:proposals[1].update(confidence='LOW',reasons=['COMPETING_LEFT_BANKS'])
        with patch('ras_workflow.bank_reach.propose_reach',return_value=(proposals,{})) as mocked:
            p=br.propose(g,d['answers'])
            self.assertEqual(mocked.call_args.args[1],{0,2})
        p.update(input_hash=br.context(g,d),created_utc='synthetic_test',project_id='synthetic_test');p['id']=br.proposal_id(p)
        return g,d,p

    def test_proposal_targets_only_inherited_controls_without_mutation(self):
        g,d,p=self.fixture();before=copy.deepcopy(g)
        self.assertEqual([r['index'] for r in p['rows']],[1])
        self.assertEqual(p['recommended_count'],1)
        self.assertEqual(p['rows'][0]['shift_ft'],[-5.,5.])
        self.assertEqual(g,before)

    def test_adoption_preserves_other_sections_and_labels_derivation(self):
        g,d,p=self.fixture();before=copy.deepcopy(d)
        new,updated=br.adopt(g,d,p,[1])
        self.assertEqual(d,before)
        self.assertEqual(new['cross_sections'][0],g['cross_sections'][0])
        self.assertEqual(new['cross_sections'][2],g['cross_sections'][2])
        row=new['cross_sections'][1]
        self.assertEqual(row['bank_stations_ft'],[20.,80.])
        self.assertEqual(row['bank_candidates']['reassessment']['previous']['value'],[25.,75.])
        self.assertFalse(updated['consent']);self.assertEqual(updated['revision'],5)
        self.assertEqual(updated['answers']['g.cross_sections.1.bank_stations_ft']['evidence_class'],'inferred')
        self.assertNotIn('inferred',bank_review.inventory(new,updated['answers'])['sections'][1]['categories'])

    def test_low_confidence_is_not_recommended_or_cleared_after_adoption(self):
        g,d,p=self.fixture(low=True)
        self.assertEqual(p['recommended_count'],0)
        new,updated=br.adopt(g,d,p,[1])
        result=bank_review.inventory(new,updated['answers'])['sections'][1]
        self.assertEqual(result['confidence'],'LOW');self.assertTrue(result['needs_attention'])
        self.assertIn('COMPETING_LEFT_BANKS',result['reasons'])

    def test_later_profile_or_bank_changes_invalidate_reassessment_context(self):
        for kind in ('profile','bank'):
            g,d,p=self.fixture();new,updated=br.adopt(g,d,p,[1]);row=new['cross_sections'][1]
            if kind=='profile':row['elevation_ft'][50]-=1
            else:row['bank_stations_ft'][0]+=1
            self.assertIn('inferred',bank_review.inventory(new)['sections'][1]['categories'])

    def test_remote_bank_change_rejects_entire_batch(self):
        g,d,p=self.fixture();g['cross_sections'][2]['bank_stations_ft'][0]+=1
        before=copy.deepcopy(g)
        with self.assertRaisesRegex(ValueError,'stale'):br.adopt(g,d,p,[1])
        self.assertEqual(g,before)

    def test_draft_change_rejects_old_context(self):
        g,d,p=self.fixture();d['revision']+=1
        with self.assertRaisesRegex(ValueError,'stale'):br.adopt(g,d,p,[1])

    def test_tampered_proposal_is_rejected(self):
        g,d,p=self.fixture();p['rows'][0]['proposed_ft'][0]+=1
        with self.assertRaisesRegex(ValueError,'stale'):br.adopt(g,d,p,[1])

    def test_mixed_unknown_duplicate_and_boolean_selections_are_atomic(self):
        for indices in ([1,2],[1,1],[True],[],None):
            g,d,p=self.fixture();before=copy.deepcopy(d)
            with self.assertRaises(ValueError):br.adopt(g,d,p,indices)
            self.assertEqual(d,before)

    def test_excludes_structure_and_segment_roughness_controls(self):
        g,d,_=self.fixture();g['structure']={'us_xs_rs':200.}
        result=br.propose(g,d['answers']);self.assertEqual(result['rows'],[])
        self.assertEqual(result['excluded'][0]['reason'],'STRUCTURE_APPROACH_CONTROL')
        g['structure']={};g['cross_sections'][1]['manning_segments']=[{'synthetic':True}]
        self.assertEqual(br.propose(g,d['answers'])['excluded'][0]['reason'],'EXPLICIT_ROUGHNESS_SUBDIVISIONS')

    def test_spatial_conflicts_remain_excluded(self):
        g,d,_=self.fixture();g['cross_sections'][1]['cutline_xy']=g['cross_sections'][0]['cutline_xy']
        result=br.propose(g,d['answers']);self.assertEqual(result['rows'],[])
        self.assertEqual(result['excluded'][0]['reason'],'GEOMETRY_CONFLICT')

    def test_persisted_preview_restores_or_reports_stale(self):
        g,d,p=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            sp=Path(tmp)/'session.json';save(sp.parent/'bank_reassessment.json',p)
            result=br.saved_preview(sp,g,d)
            self.assertEqual(result['status'],'CURRENT');self.assertNotIn('method',result['rows'][0])
            d['revision']+=1;self.assertEqual(br.saved_preview(sp,g,d)['status'],'STALE')

    def test_applied_preview_reports_success_until_another_input_changes(self):
        g,d,p=self.fixture();new,updated=br.adopt(g,d,p,[1])
        with tempfile.TemporaryDirectory() as tmp:
            sp=Path(tmp)/'session.json';save(sp.parent/'bank_reassessment.json',p)
            save(sp.parent/'bank_reassessment_applied.json',dict(proposal_id=p['id'],indices=[1],after_hash=br.context(new,updated)))
            self.assertEqual(br.saved_preview(sp,new,updated)['status'],'APPLIED')
            updated['revision']+=1;self.assertEqual(br.saved_preview(sp,new,updated)['status'],'STALE')

    def test_explicit_broader_scope_can_propose_ambiguous_saved_banks(self):
        g,d,_=self.fixture();g['cross_sections'][0]['bank_candidates'].update(confidence='LOW',reasons=['COMPETING_LEFT_BANKS'])
        with patch('ras_workflow.bank_reach.propose_reach',return_value=([local()]*3,{})) as mock:
            result=br.propose(g,d['answers'],'attention')
        self.assertEqual(mock.call_args.args[1],{2})
        self.assertEqual([r['index'] for r in result['rows']],[0,1])

    def test_adoption_persists_portable_source_evidence_and_success_receipt(self):
        g,d,p=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sp=root/'session.json';save(root/'bank_reassessment.json',p)
            m={'id':'synthetic_test','session':'session.json','revision':0}
            with patch.object(br,'ROOT',root),patch('ras_workflow.common.ROOT',root),\
                 patch('ras_workflow.intake._load',return_value=(sp,{}, {},d)),\
                 patch('ras_workflow.intake._objects',return_value=({},g)),\
                 patch('ras_workflow.app_core.persist'),patch('ras_workflow.app_core.view',return_value={'ok':True}):
                self.assertEqual(br.perform(m,'apply',dict(revision=0,proposal_id=p['id'],confirmed=True,indices=[1])),{'ok':True})
                updated=read(root/'draft.json');sources=updated['geometry_edit_sources']
                self.assertTrue(intact(sources));self.assertEqual(sources[0]['role'],'bank_reassessment')
                self.assertEqual(br.saved_preview(sp,updated['geometry'],updated)['status'],'APPLIED')
                evidence=read(root/sources[0]['path']);self.assertEqual(evidence['selected_indices'],[1])
                self.assertEqual(evidence['proposal']['id'],p['id'])
                geometry_evidence={'provenance':sources}
                self.assertEqual(br.selection_sources(geometry_evidence),sources)
                (root/sources[0]['path']).write_text('{}',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'evidence changed'):br.selection_sources(geometry_evidence)

    def test_incomplete_old_pair_can_receive_candidate_without_arithmetic_failure(self):
        g,d,_=self.fixture();g['cross_sections'][1]['bank_stations_ft']=[None,75.]
        with patch('ras_workflow.bank_reach.propose_reach',return_value=([local()]*3,{})):
            result=br.propose(g,d['answers'])
        self.assertIsNone(result['rows'][0]['shift_ft'])


if __name__=='__main__':unittest.main()
