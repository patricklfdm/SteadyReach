"""A one-sided floodplain extension must preserve the channel search location."""
import unittest
import numpy as np
from ras_workflow.banks import channel_origin, propose


class BankAnchor(unittest.TestCase):
    def test_asymmetric_extension_keeps_channel(self):
        x = np.arange(401., dtype=float)
        z = np.interp(x, [0, 40, 60, 80, 120, 140, 160, 400], [12, 12, 10, 0, 0, 10, 12, 12])
        row = dict(station_ft=x.tolist(), elevation_ft=z.tolist(),
                   cutline_xy=[[0.,0.],[400.,0.]], center_xy=[100.,0.])
        result = propose(row, dict(window_ft=10., center_search_fraction=.1, distance_penalty=1.))
        self.assertEqual(result['channel_search_origin'], 'saved_channel_anchor')
        self.assertEqual(result['channel_anchor_station_ft'], 100.)
        self.assertLessEqual(result['channel_minimum_index'], 120)
        self.assertIsNotNone(result['selected_indices'])
        left, right = result['selected_indices']
        self.assertLess(left, result['channel_minimum_index'])
        self.assertGreater(right, result['channel_minimum_index'])

    def test_bent_cutline_and_station_offset(self):
        row = dict(cutline_xy=[[0.,0.],[0.,10.],[10.,10.]], center_xy=[5.,10.])
        self.assertEqual(channel_origin(row, [20.,60.]), (50., 'saved_channel_anchor'))

    def test_unregistered_and_invalid_geometry_use_legacy_midpoint(self):
        for row in [{}, {'center_xy':[0.,0.], 'cutline_xy':[[0.,0.],[0.,0.]]},
                    {'center_xy':[float('nan'),0.], 'cutline_xy':[[0.,0.],[1.,1.]]}]:
            with self.subTest(row=row):
                self.assertEqual(channel_origin(row, [10.,90.]), (50., 'section_midpoint'))


if __name__ == '__main__':
    unittest.main()
