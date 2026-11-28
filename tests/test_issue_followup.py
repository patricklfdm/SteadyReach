import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import common, issue_followup, iteration_choice


class IssueFollowupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        for module in (common, issue_followup, iteration_choice):
            self.enterContext(patch.object(module,'ROOT',self.root))
        self.enterContext(patch.object(issue_followup.core,'folder',side_effect=lambda key:self.root/key))
        self.parent = dict(id='source', revision=3, status='RESULTS_READY')
        common.save(self.root/'base.json', {'hydraulics':{'run_id':'baseline'}})
        self.parent['summary'] = common.item(self.root/'base.json')
        self.enterContext(patch.object(issue_followup.core,'model',return_value=self.parent))
        self.enterContext(patch.object(issue_followup.core,'persist'))
        self.issue = dict(code='VERIFY_FLOW_PATH',en='Verify RS 400.',zh='核查 RS 400。',action={'tool':'comparison'})
        self.enterContext(patch('ras_workflow.result_guidance.collect',return_value={'assessment':dict(
            level=2,run_id='baseline',edition_brief=dict(next_decision=self.issue))}))
        self.body = dict(revision=3,summary_hash=self.parent['summary']['sha256'],issue_token=common.digest(self.issue))

    def test_bind_retry_and_detect_changed_question_or_original(self):
        with self.assertRaisesRegex(ValueError,'primary issue changed'):
            issue_followup.start('source',dict(self.body,issue_token='obsolete'))
        ref=issue_followup.start('source',self.body)
        self.assertEqual(issue_followup.start('source',self.body),ref)
        self.assertEqual(issue_followup.active(self.parent),ref)
        origin=dict(project_id='source',summary=self.parent['summary'],issue=ref)
        row=issue_followup.inherited_row(dict(configuration={'revision_origin':origin}))
        self.assertIn(self.issue['zh'],row['zh'])
        (self.root/ref['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'Restore'):
            issue_followup.active(self.parent)
        self.assertIn('恢复',issue_followup.inherited_row(dict(configuration={'revision_origin':origin}))['zh'])
