"""Coverage screening includes authenticated same-geometry boundary cases."""
import unittest
from unittest.mock import patch
from ras_workflow.geometry_auto_qa import boundary_study_water


class BoundaryCoverage(unittest.TestCase):
    def run_case(self, path='boundary_slopes.downstream', geometry_change=False):
        studies = [dict(analysis={'path':'analysis'}, cases=[dict(changes=[dict(path=path)])])]
        geometry = dict(cross_sections=[dict(rs=100)], flow_regime='mixed')
        summary = {'configuration':{'scenarios':[{'flow':100}]}}
        documents = {
            'analysis':dict(study={'path':'study'}, execution={'path':'execution'}),
            'study':{'cases':[dict(id='low', geometry={'path':'geometry'})]},
            'execution':{'cases':[dict(id='low', summary={'path':'summary'})]},
            'geometry':dict(geometry, cross_sections=[] if geometry_change else geometry['cross_sections']),
            'summary':dict(summary, hydraulics={})}
        rows = [dict(rs=100, left_excess_ft=2, right_excess_ft=0, wse_ft=112),
                dict(rs=100, left_excess_ft=3, right_excess_ft=0, wse_ft=113),
                dict(rs=200, left_excess_ft=0, right_excess_ft=0, wse_ft=120)]
        with patch('ras_workflow.report_studies.collect', return_value=(studies, [{'path':'verified'}])), \
             patch('ras_workflow.geometry_auto_qa.read', side_effect=lambda p:documents[p.name]), \
             patch('ras_workflow.qa_locator.collect', return_value={'rows':rows}):
            return boundary_study_water('baseline', summary, geometry)

    def test_wet_edge_envelope_and_evidence(self):
        water, sources = self.run_case()
        self.assertEqual(water, {100.:113.})
        self.assertEqual(sources, [{'path':'verified'}])

    def test_nonboundary_studies_are_excluded(self):
        self.assertEqual(self.run_case(path='channel_n'), ({}, []))

    def test_geometry_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'geometry differs'):
            self.run_case(geometry_change=True)

    def test_evidence_verification_failure_propagates(self):
        with patch('ras_workflow.report_studies.collect', side_effect=ValueError('Evidence changed')):
            with self.assertRaisesRegex(ValueError, 'Evidence changed'):
                boundary_study_water('baseline', {}, {})


if __name__ == '__main__':
    unittest.main()
