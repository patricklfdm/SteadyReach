from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from ras_workflow import team_review as team
from ras_workflow.common import save


class FormalReviewHistory(unittest.TestCase):
    def test_edited_and_malformed_history_stop_review(self):
        rows=[]
        team.append(rows,{'project':'first'},'submit','Modeler',note='review requested')
        with TemporaryDirectory() as directory:
            path=Path(directory)/'history.json'
            save(path,rows)
            self.assertEqual(team.read_history(path),rows)
            for bad in ([dict(rows[0],note='changed')], [None], {}, [{'sequence':1}]):
                with self.subTest(bad=bad):
                    save(path,bad)
                    with self.assertRaises(ValueError):team.read_history(path)

    def test_decisions_follow_only_the_selected_ancestry_and_input(self):
        rows=[]
        for owner in ('first','sibling'):
            team.append(rows,{'project':owner},'return','Reviewer',note='Check invert',station='150',
                        dependencies={'RS/150':'geometry','observations':'field'})
        decision,=team.decisions(rows,['next','first'],{'RS/150':'geometry','observations':'new','control/n':'other'})
        self.assertEqual(decision['changed'],['observations'])
        kept,=team.decisions(rows,['next','first'],{'RS/150':'geometry','observations':'field','control/n':'other'})
        self.assertEqual(kept['state'],'CARRIED')
