"""Unchanged derivations can refresh their binding without replacing user edits."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from ras_workflow import app_parameters


class CandidateRefresh(unittest.TestCase):
    def setUp(self):
        self.key = 'g.boundary_slopes.upstream'
        self.prior = dict(value=.001012, evidence_class='assumed', basis='Terrain proxy',
                          range=[.000943, .001081], source={'sha256':'original'},
                          automation_context='old', candidate='old_id')
        self.current = dict(self.prior, automation_context='new', candidate='new_id')
        self.answer = {key:self.prior[key] for key in ('value','evidence_class','basis')}
        self.answer.update(candidate_record=self.prior, confirmed=True)

    def refresh(self, candidate=None, answer=None):
        draft = dict(answers={self.key:copy.deepcopy(answer or self.answer)}, consent=True)
        model = dict(revision=2, pending_review={}, run_confirmation={})
        rows = [dict(key=self.key, parameter_candidates=[candidate or self.current])]
        with patch.object(app_parameters, 'objects', return_value=(Path('session.json'), {}, draft, {}, {})), \
             patch.object(app_parameters, 'rows', return_value=rows), \
             patch.object(app_parameters.intake, 'save_draft') as save, \
             patch('ras_workflow.app_core.persist') as persist:
            result = app_parameters.refresh_equivalent_candidates(model)
        return result, draft, model, save, persist

    def test_equivalent_rebind_is_audited_and_invalidates_confirmation(self):
        result, draft, model, save, persist = self.refresh()
        self.assertEqual(len(result), 1)
        self.assertEqual(draft['answers'][self.key]['value'], .001012)
        self.assertEqual(draft['answers'][self.key]['candidate_record'], self.current)
        self.assertFalse(draft['consent'])
        self.assertNotIn('run_confirmation', model)
        self.assertEqual(model['revision'], 3)
        save.assert_called_once()
        self.assertEqual(persist.call_args.args[1], 'REFRESH_EQUIVALENT_CANDIDATES')

    def test_material_changes_remain_for_explicit_review(self):
        for key, value in [('value', .002), ('basis', 'Different proxy'),
                           ('range', [.0005, .002]), ('source', {'sha256':'replaced'}),
                           ('evidence_class', 'reported')]:
            with self.subTest(key=key):
                result, _, model, save, _ = self.refresh(dict(self.current, **{key:value}))
                self.assertEqual(result, [])
                self.assertEqual(model['revision'], 2)
                save.assert_not_called()

    def test_manual_edit_or_reclassification_is_preserved(self):
        for key, value in [('value', .0015), ('basis', 'User adjustment'), ('evidence_class', 'reported')]:
            with self.subTest(key=key):
                result, draft, _, save, _ = self.refresh(answer=dict(self.answer, **{key:value}))
                self.assertEqual(result, [])
                self.assertEqual(draft['answers'][self.key][key], value)
                save.assert_not_called()

    def test_current_binding_is_idempotent(self):
        result, _, _, save, _ = self.refresh(candidate=self.prior)
        self.assertEqual(result, [])
        save.assert_not_called()

    def test_final_review_binds_after_refresh(self):
        draft = dict(answers={self.key:copy.deepcopy(self.answer)}, consent=True)
        model = dict(id='test', revision=2)
        fields = [dict(key=self.key, parameter_candidates=[self.current])]
        with patch.object(app_parameters, 'objects', return_value=(Path('session.json'), {}, draft, {}, {})), \
             patch.object(app_parameters, 'rows', return_value=fields), \
             patch.object(app_parameters.intake, 'save_draft'), \
             patch.object(app_parameters, 'reviewed_draft', return_value=(Path('session.json'), draft)), \
             patch.object(app_parameters.intake, 'validate', return_value={'errors':[]}), \
             patch.object(app_parameters, 'binding', side_effect=lambda m:dict(geometry={}, revision=m['revision'])), \
             patch.object(app_parameters, 'attention', return_value=[]), \
             patch.object(app_parameters, 'save'), \
             patch.object(app_parameters, 'item', return_value={'sha256':'token'}), \
             patch.object(app_parameters, 'rel', return_value='parameters.json'), \
             patch('ras_workflow.app_automation.preflight', return_value={'issues':[]}), \
             patch('ras_workflow.app_core.require_idle'), \
             patch('ras_workflow.app_core.folder', return_value=Path('test')), \
             patch('ras_workflow.app_core.persist'):
            packet = app_parameters.review(model)
        self.assertEqual(packet['revision'], 3)
        self.assertEqual(packet['inputs']['revision'], 3)
        self.assertEqual(packet['refreshed_equivalent_fields'], [self.key])
        self.assertTrue(packet['ready'])


if __name__ == '__main__':
    unittest.main()
