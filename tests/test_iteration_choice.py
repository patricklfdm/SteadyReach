from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ras_workflow import app_core, common, iteration_choice, recipient_handoff


class IterationChoices(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for obj, name, value in [(common, 'ROOT', root), (app_core, 'ROOT', root),
                                 (app_core, 'BASE', root/'projects'), (iteration_choice, 'ROOT', root)]:
            self.enterContext(patch.object(obj, name, value))
        self.models = {}
        for key in ('baseline', 'revision'):
            directory = root / 'projects' / key
            path = directory / 'summary.json'
            common.save(path, {'case': key})
            record = dict(id=key, status='RESULTS_READY', revision=2, summary=common.item(path))
            if key == 'revision':
                record['parent_revision'] = dict(project_id='baseline', summary=self.models['baseline']['summary'])
            common.save(directory/'app.json', record)
            self.models[key] = record
        self.body = dict(revision=2, summary_hash=self.models['revision']['summary']['sha256'])

    def test_broken_choice_can_be_replaced_without_losing_the_result(self):
        path = app_core.folder('revision')/'review'/'iteration_choice.json'
        path.parent.mkdir()
        path.write_text('{', encoding='utf-8')
        self.assertEqual(iteration_choice.latest(self.models['revision'])['choice'], 'unavailable')
        with self.assertRaisesRegex(ValueError, 'saved edition choice'):
            recipient_handoff.export('revision', self.body)
        result = iteration_choice.choose('revision', {**self.body, 'choice':'review'})
        self.assertEqual(iteration_choice.latest(self.models['revision']), result)

    def test_pause_survives_reload_and_stale_decision_does_not_replace_it(self):
        paused = iteration_choice.choose('revision', {**self.body, 'choice': 'wait'})
        self.assertEqual(iteration_choice.latest(app_core.model('revision')), paused)
        self.assertEqual(iteration_choice.choose('revision', {**self.body, 'choice': 'wait'}), paused)
        with self.assertRaisesRegex(ValueError, 'another tab'):
            iteration_choice.choose('revision', {**self.body, 'choice': 'review'})
        with self.assertRaisesRegex(ValueError, 'Resume this review'):
            recipient_handoff.export('revision', self.body)
        resumed = iteration_choice.choose('revision', {**self.body, 'choice':'review', 'previous':paused['token']})
        self.assertIsNone(resumed['selected'])
        self.assertIsNone(iteration_choice.latest({**self.models['revision'], 'summary':self.models['baseline']['summary']}))

    def test_choose_only_a_comparable_pair_and_handoff_the_selected_run(self):
        with patch.object(iteration_choice, 'compare', return_value={'status':'COMPARISON_UNAVAILABLE'}):
            with self.assertRaisesRegex(ValueError, 'comparable'):
                iteration_choice.choose('revision', {**self.body, 'choice':'current'})
        with patch.object(iteration_choice, 'compare', return_value={'status':'COMPARISON_NOT_ACCEPTANCE','profiles':[{}]}):
            record=iteration_choice.choose('revision', {**self.body, 'choice':'parent'})
            self.assertEqual(record['selected']['summary'], self.models['baseline']['summary'])
            with self.assertRaisesRegex(ValueError, 'selected baseline'):
                recipient_handoff.export('revision', self.body)
            changed=iteration_choice.choose('revision', {**self.body, 'choice':'current','previous':record['token']})
            self.assertEqual(changed['selected']['summary'], self.models['revision']['summary'])
