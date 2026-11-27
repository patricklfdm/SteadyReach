import unittest
import numpy as np
from examples.enterprise_pilot.big_river_blind import register_points


class SpatialHoldout(unittest.TestCase):
    def setUp(self):
        self.sections=[dict(rs=100+i,center_xy=[i,0],cutline_xy=[[i,-10],[i,10]]) for i in (180,120,60,0)]
        self.axis=np.array([-1.,0.])

    def test_two_end_sections_and_duplicate_measurements(self):
        xy=np.array([[0,0],[0,0],[1.5,2],[60,0],[120,20],[180,1]])
        registered=register_points(xy,self.sections,self.axis)
        self.assertEqual([(p['role'],p['rs'],p['source_line']) for p in registered],
                         [('outlet',100,2),('holdout',160,5)])

    def test_nearby_observation_cannot_replace_missing_outlet(self):
        xy=np.array([[4,0],[60,2],[120,1]])
        self.assertEqual(register_points(xy,self.sections,self.axis),[])
