"""Reference coverage controls and extension provenance regressions."""
import copy
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import numpy as np

from ras_workflow.section_reference import prepare
from ras_workflow.geometry_auto_qa import extend
from ras_workflow import app_geometry_auto


class ReferenceCoverage(unittest.TestCase):
    def setUp(self):
        self.geometry = dict(model_type='river', vertical_datum='TEST_DATUM', cross_sections=[
            dict(rs=rs, center_xy=[0., y]) for rs, y in [(900, 0), (800, 10), (700, 30), (100, 100)]])
        self.model = dict(attachments=[dict(path='reference.pdf', sha256='test')])
        self.request = dict(source_path='reference.pdf', vertical_datum='TEST_DATUM',
            points=[dict(rs=800, water_ft=110), dict(rs=100, water_ft=101)])

    def test_interpolation_uses_distance_and_holds_end_control(self):
        with patch('ras_workflow.section_reference.intact', return_value=True):
            result = prepare(self.model, self.geometry, self.request)
        self.assertEqual([v['water_ft'] for v in result['sections']], [110., 110., 108., 101.])
        self.assertEqual(result['purpose'], 'SECTION_EXTENT_SCREEN_ONLY')
        self.assertFalse(result['solver_run'])

    def test_stale_source_and_wrong_datum_are_rejected(self):
        with patch('ras_workflow.section_reference.intact', return_value=False), self.assertRaises(ValueError):
            prepare(self.model, self.geometry, self.request)
        invalid = dict(self.request, vertical_datum='OTHER_DATUM')
        with self.assertRaises(ValueError):
            prepare(self.model, self.geometry, invalid)

    def test_unknown_duplicate_and_nonfinite_controls_are_rejected(self):
        cases = [[dict(rs=800, water_ft=110), dict(rs=999, water_ft=101)],
                 [dict(rs=800, water_ft=110), dict(rs=800, water_ft=101)],
                 [dict(rs=800, water_ft=110), dict(rs=100, water_ft=float('nan'))]]
        with patch('ras_workflow.section_reference.intact', return_value=True):
            for points in cases:
                with self.subTest(points=points), self.assertRaises(ValueError):
                    prepare(self.model, self.geometry, dict(self.request, points=points))

    def test_extension_keeps_original_samples_and_bank_coordinates(self):
        class Sampler:
            factor = 1.
            cell_ft = 1.
            def sample(self, xy):
                return np.maximum(0., np.abs(xy[:, 0])-10.)
            def stamp(self, row):
                row['terrain_sampling'] = {'test': True}
        row = dict(cutline_xy=[[-10., 0.], [10., 0.]], center_xy=[0., 0.],
            station_ft=[0., 5., 10., 15., 20.], elevation_ft=[0., 0., 0., 0., 0.],
            bank_stations_ft=[5., 15.])
        original = copy.deepcopy(row)
        new, record = extend(row, Sampler(), 5., 100.)
        self.assertEqual(row, original)
        shift = record['station_label_shift_ft']
        for x, z in zip(row['station_ft'], row['elevation_ft']):
            self.assertEqual(new['elevation_ft'][new['station_ft'].index(x+shift)], z)
        self.assertEqual(new['bank_stations_ft'], [v+shift for v in row['bank_stations_ft']])
        self.assertTrue(min(new['elevation_ft'][0], new['elevation_ft'][-1]) > 5.)

    def test_confirmed_unchanged_banks_stop_automatic_replacement(self):
        row = dict(rs=100., station_ft=[0., 1., 2., 3.], elevation_ft=[5., 0., 0., 5.],
            bank_stations_ft=[1., 2.], cutline_xy=[[0., 0.], [3., 0.]], center_xy=[1.5, 0.])
        old = dict(model_type='river', cross_sections=[row])
        field = 'g.cross_sections.0.bank_stations_ft'
        draft = dict(revision=17, answers={field:dict(value=[1., 2.], automatic_preparation=True)}, geometry=old)
        layout = dict(id='layout', can_apply=True, geometry=copy.deepcopy(old), changed_sections=[0])
        proposal = dict(id='proposal', token='token', mode='qa', layouts=[layout], sources=[])
        model = dict(id='isolated', revision=21)
        with patch.object(app_geometry_auto, 'load_pending', return_value=proposal), \
             patch.object(app_geometry_auto.params, 'objects', return_value=(Path('session.json'), None, draft, None, old)), \
             patch.object(app_geometry_auto, 'spatial_issues', return_value=[]), \
             patch('ras_workflow.app_automation.preflight', return_value={'issues':[]}), \
             patch.object(app_geometry_auto, 'item', return_value={}), \
             patch.object(app_geometry_auto, 'lock', return_value=nullcontext()), \
             patch.object(app_geometry_auto, 'read', return_value={'revision':17}), \
             patch.object(app_geometry_auto, 'save'), \
             patch.object(app_geometry_auto.core, 'persist'), \
             patch.object(app_geometry_auto.core, 'view', return_value={}):
            app_geometry_auto.apply(model, dict(proposal_id='proposal', token='token', layout_id='layout',
                confirmed=True, confirm_banks=True, banks={'0':[1., 2.]}))
        self.assertNotIn(field, draft['answers'])
        self.assertEqual(draft['geometry']['cross_sections'][0]['bank_stations_ft'], [1., 2.])


if __name__ == '__main__':
    unittest.main()
