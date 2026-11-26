"""Regression coverage for native downstream stages and honest pilot denominators."""
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from pilot_metrics import by_route, nearest_p95
from ras_workflow import native_review


class PilotTests(unittest.TestCase):
    def test_stage_is_profile_specific_and_finite(self):
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'set'
            shutil.copytree(ROOT/'examples/phelps_brook/inputs',source)
            flow=source/'Phelps_River.f01'
            value=flow.read_text(encoding='ascii').replace('Dn Type= 3','Dn Type= 1',1).replace('Dn Slope=0.175','Dn Known WS=1082.4',1)
            flow.write_text(value,encoding='ascii')
            project=source/'Phelps_River.prj'
            actual=native_review.inspect(project,selected_plan='p01')
            self.assertEqual(actual['expected_native']['imported_downstream_stages_ft'],{'1':1082.4})
            self.assertEqual(actual['boundaries'][1]['downstream'],dict(type=3,slope=.175))
            flow.write_text(value.replace('Dn Known WS=1082.4','Dn Known WS=NaN'),encoding='ascii')
            with self.assertRaisesRegex(ValueError,'finite'):
                native_review.inspect(project,selected_plan='p01')

    def test_storage_keeps_similarly_named_sibling_as_dependency(self):
        from ras_workflow.common import save
        from ras_workflow.storage_inventory import references,regular_tree
        with TemporaryDirectory() as directory:
            root=Path(directory).resolve();own=root/'projects/site';other=root/'projects/site_revision'
            save(own/'sub'/'notes.json',dict(inside='projects/site/document.pdf',other='projects/site_revision/source.pdf',
                                            relative='../../site_revision/source.pdf',outside='../outside.json'))
            targets=references(root,own,regular_tree(own))
            self.assertEqual(targets,{other/'source.pdf'})

    def test_blocker_and_recovered_delivery_have_separate_denominators(self):
        rows=[dict(route='survey',expected='BLOCKED',outcome='BLOCKED'),
              dict(route='survey',expected='BLOCKED',outcome='PAIR'),
              dict(route='survey',expected='PAIR',outcome='PAIR',verified_pair=True,first_pass_pair=False)]
        total=by_route(rows)['survey']
        self.assertEqual((total['requested'],total['eligible'],total['first_pass_pairs'],total['final_pairs']),(3,1,0,1))
        self.assertEqual((total['seeded_blockers'],total['detected_blockers'],total['false_ready']),(2,1,1))
        self.assertEqual(nearest_p95([3,2]),3)
        self.assertIsNone(nearest_p95([]))
