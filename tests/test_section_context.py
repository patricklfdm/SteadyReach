"""Coverage and profile separation for the linked section view."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ras_workflow import section_context as context, inputs
from test_river_contract import river


class SectionContextTests(unittest.TestCase):
    def test_survey_stationing_requires_explicit_survey_and_caller(self):
        geometry = river()
        geometry.update(horizontal_crs='LOCAL_CS["Chainage",LOCAL_DATUM["Local",0],UNIT["foot",0.3048]]',
                        map_reference='local_survey_chainage', channel_geometry_basis='surveyed_channel')
        def crs_errors(enabled):
            return [e for e in inputs.geometry_errors(geometry, True, survey_stationing_only=enabled)
                    if 'CRS' in e or 'horizontal_crs' in e]
        self.assertTrue(crs_errors(False))
        self.assertEqual(crs_errors(True), [])
        geometry['channel_geometry_basis'] = 'conditional_surface_dem'
        self.assertTrue(crs_errors(True))

    def test_boundary_series_preserves_sign_profile_and_case(self):
        change = dict(path='boundary_slopes.downstream', before=.01, after=.02)
        cases = [dict(id='slope', changes=[change]), dict(id='combined', changes=[change, change])]
        rows = [dict(profile='Q10', station='100.00', delta_wse_ft=0.0),
                dict(profile='Q100', station='100', delta_wse_ft=-1.25)]
        comparisons = [dict(case=case['id'], cross_section_differences=rows) for case in cases]
        results = context.boundary_series([dict(cases=cases, comparisons=comparisons, analysis='test')])
        self.assertEqual([(r['profile'],r['by_rs']) for r in results],
                         [('Q10',{'100':0.0}), ('Q100',{'100':-1.25})])

    def test_offline_missing_does_not_fetch_or_imply_zero_records(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(context, 'query') as fetch:
            layers = context.public_lines(Path(directory), [540000,4100000,540100,4100300], 'EPSG:32610', False)
            fetch.assert_not_called()
            self.assertEqual(len(layers), 4)
            self.assertEqual({r['status'] for r in layers}, {'NOT_LOADED'})

    def test_changed_delivery_is_not_used_as_a_basemap(self):
        model = dict(summary={'sha256':'new'}, latest_delivery={'summary':{'sha256':'old'}})
        self.assertEqual(context.backdrop(model, [], '')['status'], 'NO_MATCHING_DELIVERY')
