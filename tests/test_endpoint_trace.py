"""Regression coverage for optional endpoint-only river tracing (screening geometry)."""
import unittest
from unittest.mock import patch
import numpy as np

from ras_workflow import river_layout


class Terrain:
    factor = 1.
    cell_ft = 2.

    def sample(self, points):
        x, y = np.asarray(points).T
        center = 40. * np.sin(np.pi * x / 400.)
        return .07 * np.abs(y - center) - .02 * x


class EndpointTraceTests(unittest.TestCase):
    ends = np.array([[0., 0.], [400., 0.]])

    def test_consistent_bend_previews_two_supported_flanks(self):
        line, _, evidence = river_layout.trace(self.ends, Terrain())
        screen = evidence['endpoint_search']
        self.assertFalse(screen['needs_bend_anchor'])
        self.assertGreater(np.max(line[:, 1]), 20.)
        self.assertLessEqual(screen['path_difference_ft'], screen['tolerance_ft'])

    def test_flat_surface_needs_an_interior_control(self):
        terrain = Terrain()
        terrain.sample = lambda points: np.zeros(len(points))
        _, _, evidence = river_layout.trace(self.ends, terrain)
        self.assertTrue(evidence['endpoint_search']['needs_bend_anchor'])
        self.assertEqual(evidence['endpoint_search']['supported_flanks'], 0)

    def test_missing_terrain_and_unusable_extent(self):
        terrain = Terrain()
        terrain.sample = lambda points: np.full(len(points), np.nan)
        with self.assertRaises(ValueError):
            river_layout.trace(self.ends, terrain)
        with self.assertRaises(ValueError):
            river_layout.trace(self.ends * 0., Terrain())

    def test_disagreement_across_corridors_keeps_a_decision_open(self):
        x = np.arange(0., 401., 5.)
        narrow = np.column_stack([x, np.zeros_like(x)])
        wide = np.column_stack([x, 50. * np.sin(np.pi * x / 400.)])
        with patch.object(river_layout, 'corridor_grid', side_effect=[
                (narrow, None, {}), (wide, None, {})]):
            _, _, evidence = river_layout.trace(self.ends, Terrain())
        screen = evidence['endpoint_search']
        self.assertGreater(screen['path_difference_ft'], screen['tolerance_ft'])
        self.assertTrue(screen['needs_bend_anchor'])

    def test_existing_bend_controls_retain_original_search(self):
        anchors = np.insert(self.ends, 1, [200., 30.], axis=0)
        with patch.object(river_layout, 'corridor_grid', return_value='original') as grid:
            self.assertEqual(river_layout.trace(anchors, Terrain()), 'original')
        self.assertEqual(grid.call_count, 1)
        np.testing.assert_array_equal(grid.call_args.args[0], anchors)
        self.assertEqual(grid.call_args.args[1:3], (40., 5.))
