"""Changed derivations require explicit, fresh, atomic user choices."""
import copy
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from ras_workflow import app_dependency_review as decisions, app_automation, app_parameters
from ras_workflow.common import digest


class DependencyReviewTests(unittest.TestCase):
    def setUp(self):
        self.key = 'g.boundary_slopes.downstream'
        self.model = dict(id='test', revision=3, pending_review=dict(path='review.json', sha256='token'),
                          run_confirmation={'sha256':'old'}, status='INPUTS_READY')
        self.prior = dict(value=.011647, evidence_class='assumed', basis='Old terrain proxy',
                          candidate_record=dict(value=.011647, automation_context='old'))
        self.draft = dict(revision=2, answers={self.key:copy.deepcopy(self.prior)}, consent=True)
        self.candidate = dict(candidate='new', value=.006, evidence_class='assumed',
                              basis='Current terrain proxy', automation_context='context')
        self.field = dict(key=self.key, missing=False, value=.011647, suggestions=[],
                          parameter_candidates=[self.candidate])
        self.bound = {'geometry':{}, 'revision':3}
        self.packet = dict(fields=[self.field], fingerprint=digest(self.bound), ready=False)

    def resolve(self, selections, token='token', bound=None):
        with ExitStack() as stack:
            def mocked(target, **kwargs):
                return stack.enter_context(patch(target, **kwargs))
            mocked('ras_workflow.app_core.model', return_value=self.model)
            mocked('ras_workflow.app_core.require_idle')
            mocked('ras_workflow.app_dependency_review.intact', return_value=True)
            mocked('ras_workflow.app_dependency_review.read', return_value=self.packet)
            mocked('ras_workflow.app_parameters.binding', return_value=bound or self.bound)
            mocked('ras_workflow.app_parameters.objects', return_value=(Path('session.json'), {}, self.draft, {}, {}))
            mocked('ras_workflow.app_parameters.rows', return_value=[self.field])
            mocked('ras_workflow.app_dependency_review.dependency', return_value='context')
            mocked('ras_workflow.app_dependency_review.preflight', return_value={'issues':[dict(code='DERIVED_INPUT_CHANGED',field=self.key)]})
            mocked('ras_workflow.intake._objects', return_value=({},{}))
            self.save = mocked('ras_workflow.intake.save_draft')
            self.persist = mocked('ras_workflow.app_core.persist')
            return decisions.resolve('test', dict(revision=3,review_token=token,selections=selections))

    def test_current_candidate_requires_new_confirmation_and_retains_origin(self):
        result = self.resolve([dict(field=self.key,action='candidate',candidate='new')])
        saved = self.save.call_args.args[1]
        answer = saved['answers'][self.key]
        self.assertEqual(answer['value'], .006)
        self.assertEqual(answer['candidate_record'], self.candidate)
        self.assertEqual(answer['dependency_review']['previous_answer'], self.prior)
        self.assertFalse(saved['consent'])
        self.assertFalse(answer['confirmed'])
        self.assertNotIn('pending_review',self.model)
        self.assertNotIn('run_confirmation',self.model)
        self.assertEqual(result['saved_fields'],[self.key])
        self.assertEqual(self.draft['answers'][self.key],self.prior)

    def test_retaining_old_value_is_assumption_with_new_dependency_watch(self):
        self.resolve([dict(field=self.key,action='retain')])
        answer = self.save.call_args.args[1]['answers'][self.key]
        self.assertEqual(answer['value'],.011647)
        self.assertEqual(answer['evidence_class'],'assumed')
        self.assertNotIn('candidate_record',answer)
        self.assertEqual(answer['dependency_review']['context'],'context')
        geometry=dict(cross_sections=[],structure={'groups':[]})
        with patch.object(app_automation,'resolve',return_value=([],[])), \
             patch.object(app_automation,'surveys',return_value=[]), \
             patch.object(app_automation,'association_suggestions',return_value=([],[])), \
             patch.object(app_parameters,'objects',return_value=(None,None,{'answers':{self.key:answer}},None,geometry)), \
             patch.object(app_automation,'dependency',return_value='changed-again'):
            check=app_automation.preflight({'session':'session.json'},geometry)
        self.assertEqual(check['issues'][0]['field'],self.key)
        self.assertTrue(check['issues'][0]['blocking'])

    def test_invalid_batch_does_not_save_any_part(self):
        for selections in [[],[dict(field=self.key,action='candidate',candidate='stale')],
                           [dict(field=self.key,action='skip')],
                           [dict(field=self.key,action='retain'),dict(field=self.key,action='retain')],
                           [dict(field=self.key,action='retain'),dict(field='unknown',action='retain')]]:
            with self.subTest(selections=selections), self.assertRaises(ValueError):
                self.resolve(selections)
            self.save.assert_not_called()
            self.persist.assert_not_called()

    def test_stale_page_or_changed_sources_cannot_apply_decisions(self):
        for kwargs in [dict(token='old-token'),dict(bound={'geometry':{'edited':True}})]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError,'refresh'):
                self.resolve([dict(field=self.key,action='retain')],**kwargs)
            self.save.assert_not_called()

    def test_completed_project_is_not_editable(self):
        self.model['active_project']='approved/project.json'
        with self.assertRaisesRegex(ValueError,'editable revision'):
            self.resolve([dict(field=self.key,action='retain')])
        self.save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
