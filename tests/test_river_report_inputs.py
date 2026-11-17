"""River report readback keeps native precision without widening import scope."""
import tempfile
import re
import unittest
from pathlib import Path
from ras_workflow import native, native_review
from ras_workflow.report_native_river import inspect
from test_river_contract import river


class RiverReportInputs(unittest.TestCase):
    def build(self, folder, geometry):
        return native.build(Path(folder)/'model',
            dict(project_id='report_verification',case_kind='software_validation'),
            dict(id='q100',channel_n=.0425,overbank_n=.11,
                 profiles=[dict(id='Q100',flow_cfs=100)]), geometry)[0]

    def test_normal_depth_precision_and_import_scope(self):
        geometry=river();geometry['boundary_slopes']['downstream']=.011647
        with tempfile.TemporaryDirectory() as folder:
            project=self.build(folder,geometry);result=inspect(project)
            self.assertEqual(len(result['sections']),len(geometry['cross_sections']))
            self.assertEqual(result['sections'][0]['manning'][1][1],.0425)
            self.assertEqual(result['boundaries'][0]['downstream']['slope'],.011647)
            self.assertEqual(result['profiles'][0]['flow_cfs'],100)
            with self.assertRaisesRegex(ValueError,'culvert crossing'):
                native_review.inspect(project)

    def test_known_stage_and_unused_upstream(self):
        geometry=river();geometry['flow_regime']='subcritical'
        geometry['boundaries']['downstream']=dict(type='known_stage',stages_ft=[104.125])
        with tempfile.TemporaryDirectory() as folder:
            result=inspect(self.build(folder,geometry))
            self.assertEqual(result['boundaries'][0]['downstream'],dict(type=1,stage_ft=104.125))
            self.assertEqual(result['boundaries'][0]['upstream'],dict(type=0))

    def test_structure_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            project=self.build(folder,river());path=project.with_suffix('.g01')
            text=path.read_text(encoding='ascii')
            changed,n=re.subn(r'(Type RM Length L Ch R =\s*)1\s*,',r'\g<1>2,',text,count=1)
            self.assertEqual(n,1)
            path.write_text(changed,encoding='ascii')
            with self.assertRaisesRegex(ValueError,'cross sections only'):inspect(project)


if __name__=='__main__':unittest.main()
