"""Joint section proposals retain geometry, sampling and bounded-search safeguards."""
import copy
import itertools
import random
import unittest
from unittest.mock import patch

import numpy as np

from ras_workflow.common import digest
from ras_workflow.geometry_auto_qa import extend, terrain_owned
from ras_workflow.geometry_qa import spatial_issues
from ras_workflow.section_joint import repair, flow_crossing, _select, _crosses


class Sampler:
    factor = 1.
    cell_ft = 1.
    source = {'sha256': 'unit-test-raster'}
    unit = 'ft'
    datum = 'TEST'

    def sample(self, points):
        return np.maximum(0., np.abs(points[:, 0]) - 10.)

    def stamp(self, row):
        keys = ('cutline_xy', 'station_ft', 'elevation_ft', 'center_xy')
        row['terrain_sampling'] = dict(raster=self.source, vertical_unit=self.unit,
            vertical_datum=self.datum, spatial_fingerprint=digest({k: row[k] for k in keys}))


def fixture():
    sampler = Sampler()
    rows = []
    for rs, cut, center in [(200., [[-10., -2.], [10., 2.]], [0., 0.]),
                            (100., [[-10., 9.], [10., 5.]], [0., 7.])]:
        cut = np.array(cut)
        width = float(np.linalg.norm(cut[1] - cut[0]))
        points = cut[0] + np.linspace(0, 1, 21)[:, None] * (cut[1] - cut[0])
        row = dict(rs=rs, reach_id='river', cutline_xy=cut.tolist(), center_xy=center,
                   station_ft=np.linspace(0, width, 21).tolist(),
                   elevation_ft=sampler.sample(points).tolist(), bank_stations_ft=[5., 15.])
        sampler.stamp(row)
        rows.append(row)
    return dict(horizontal_crs='+proj=utm +zone=13 +datum=NAD83 +units=ft +no_defs',
                cross_sections=rows, flowlines=[dict(id='river', xy=[[0., -100.], [0., 100.]])]), sampler


class JointSections(unittest.TestCase):
    def test_coupled_coverage_and_rotation_with_actual_sampling(self):
        geometry, sampler = fixture()
        before = copy.deepcopy(geometry)
        result = repair(geometry, sampler, {200.: 10., 100.: 10.}, 100.)
        self.assertEqual(geometry, before)
        self.assertFalse(result['unresolved'])
        self.assertFalse(spatial_issues(result['geometry']['cross_sections']))
        self.assertTrue(any(c['rotation_deg'] for c in result['changes']))
        for row in result['geometry']['cross_sections']:
            self.assertGreater(min(row['elevation_ft'][0], row['elevation_ft'][-1]), 10.)
            self.assertLessEqual(row['station_ft'][-1] - row['station_ft'][0], 100.)
            self.assertTrue(terrain_owned(row, sampler))
            self.assertIsNotNone(flow_crossing(row['cutline_xy'], geometry['flowlines'][0]['xy']))
            change = next(c for c in result['changes'] if c['rs'] == row['rs'])
            if change['rotation_deg']:
                self.assertIsNone(row['bank_stations_ft'])
                self.assertFalse(change['old_points_preserved'])

    def test_protected_and_nonterrain_geometry_stays_fixed(self):
        geometry, sampler = fixture()
        geometry['cross_sections'][1].pop('terrain_sampling')
        result = repair(geometry, sampler, {200.: 10., 100.: 10.}, 100., protected={0})
        self.assertEqual(result['geometry'], geometry)
        self.assertEqual(len(result['unresolved']), 2)

    def test_invalid_profiles_are_retained_for_review(self):
        geometry, sampler = fixture()
        geometry['cross_sections'][0]['elevation_ft'][0] = None
        result = repair(geometry, sampler, {200.: 10.}, 100.)
        self.assertEqual(result['geometry'], geometry)
        self.assertEqual(result['unresolved'][0]['code'], 'INVALID_SECTION_PROFILE')

    def test_nodata_never_becomes_a_rotated_profile(self):
        geometry, sampler = fixture()
        sampler.sample = lambda points: np.full(len(points), np.nan)
        result = repair(geometry, sampler, {200.: 10., 100.: 10.}, 100.)
        self.assertEqual(result['geometry'], geometry)
        self.assertFalse(result['changes'])

    def test_flowline_vertex_is_one_crossing_and_meander_is_rejected(self):
        cut = [[-5., 0.], [5., 0.]]
        self.assertEqual(flow_crossing(cut, [[0., -5.], [0., 0.], [0., 5.]]), 5.)
        self.assertIsNone(flow_crossing(cut, [[-3., -5.], [-3., 5.], [3., 5.], [3., -5.]]))
        self.assertIsNone(flow_crossing(cut, [[-3., 0.], [3., 0.]]))
        self.assertTrue(_crosses(cut, [[-10., 5.], [0., 0.], [10., 5.]]))

    def test_joint_search_revises_neighbor_instead_of_accepting_conflict(self):
        def option(cut, cost):
            return dict(row={'cutline_xy':cut}, record=None, cost=cost)
        options = {
            0: [option([[-5., 0.], [5., 0.]], (1, 0., 0.)),
                option([[-5., 2.], [5., 2.]], (0, 1., 0.))],
            1: [option([[0., 1.], [0., 3.]], (0, 0., 0.)),
                option([[6., 1.], [6., 3.]], (0, 1., 0.))]}
        selected, trials = _select(options)
        self.assertEqual(selected, {0:1, 1:1})
        self.assertFalse(trials[0]['search_limit_reached'])
        with patch('ras_workflow.section_joint.MAX_SEARCH_NODES', 1):
            selected, trials = _select(options)
        self.assertFalse(selected)
        self.assertEqual(trials[0]['visited'], 1)
        self.assertTrue(trials[0]['search_limit_reached'])

    def test_one_sided_extension_can_use_available_total_width(self):
        sampler = Sampler()
        sampler.sample = lambda points: np.where(points[:, 0] > 70., 10., 0.)
        row = dict(cutline_xy=[[0., 0.], [20., 0.]], center_xy=[10., 0.],
                   station_ft=[0., 10., 20.], elevation_ft=[10., 0., 0.])
        result, record = extend(row, sampler, 5., 100.)
        self.assertIsNotNone(result)
        self.assertGreater(record['right_added_ft'], 40.)
        self.assertEqual(record['left_added_ft'], 0.)
        self.assertLessEqual(result['station_ft'][-1], 100.)

    def test_partial_coverage_fallback_keeps_feasible_geometry(self):
        options = {}
        for index, y in enumerate((0., 2.)):
            options[index] = [
                dict(row={'cutline_xy':[[-5., y], [5., y]]}, record=None, cost=(1, 0., 0.)),
                dict(row={'cutline_xy':[[-5., 1.], [5., 1.]]}, record=None, cost=(0, 1., 0.))]
        selected, _ = _select(options)
        self.assertEqual(len(selected), 2)
        self.assertEqual(sum(options[i][a]['cost'][0] for i,a in selected.items()), 1)

    def test_small_joint_search_matches_exhaustive_cost(self):
        rng = random.Random(17)
        for trial in range(15):
            options = {}
            for index in range(3):
                options[index] = [dict(row={'cutline_xy':[
                    [-5., index*5+rng.uniform(-4,4)], [5., index*5+rng.uniform(-4,4)]]},
                    record=None, cost=(rng.randrange(2), float(angle), rng.random()))
                    for angle in range(3)]
            feasible = []
            for choices in itertools.product(range(3), repeat=3):
                if any(_crosses(options[i][choices[i]]['row']['cutline_xy'],
                                options[j][choices[j]]['row']['cutline_xy'])
                       for i,j in itertools.combinations(range(3), 2)):
                    continue
                feasible.append(tuple(sum(options[i][choices[i]]['cost'][k] for i in range(3)) for k in range(3)))
            selected, _ = _select(options)
            with self.subTest(trial=trial):
                if feasible:
                    actual = tuple(sum(options[i][selected[i]]['cost'][k] for i in range(3)) for k in range(3))
                    self.assertEqual(actual, min(feasible))
                else:
                    self.assertLess(len(selected), 3)

    def test_two_sided_extension_respects_total_bound(self):
        sampler = Sampler()
        sampler.sample = lambda points: np.where(np.abs(points[:, 0]) > 30., 10., 0.)
        row = dict(cutline_xy=[[-10., 0.], [10., 0.]], center_xy=[0., 0.],
                   station_ft=[0., 10., 20.], elevation_ft=[0., 0., 0.])
        result, record = extend(row, sampler, 5., 60.)
        self.assertIsNone(result)
        self.assertEqual(record['status'], 'REQUIRED_WIDTH_EXCEEDS_BOUND')


if __name__ == '__main__':
    unittest.main()
