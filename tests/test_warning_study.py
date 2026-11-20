"""Bounded warning ranking, protected geometry and conditional connectivity."""
import unittest
from copy import deepcopy
from unittest.mock import patch

import numpy as np

from ras_workflow import warning_geometry as geo, warning_study as study
from test_river_contract import river


class FlatTerrain:
    factor = 1/.3048
    cell_ft = factor
    def sample(self,xy):
        return np.full(len(xy),113.)
    def stamp(self,row):
        pass


def geometry():
    g=river()
    rows=g['cross_sections']
    g['flowlines']=[{'xy':[r['center_xy'] for r in rows]}]
    return g


class WarningReview(unittest.TestCase):
    def test_positive_margin_is_checked_even_with_no_wet_ends(self):
        g=geometry();before=deepcopy(g)
        out,changes,_=geo.extend_ends(g,{r['rs']:109.9 for r in g['cross_sections']},FlatTerrain(),300,.30,True)
        self.assertEqual(len(changes),8)
        self.assertEqual(g,before)
        self.assertTrue(geo.validate_layout(g,out))
        self.assertTrue(all(r['elevation_ft'][0]==113 for r in out['cross_sections']))

    def test_tampered_channel_and_reach_partition_are_rejected(self):
        g=geometry()
        refined,changes,_=geo.infill(g,{300.:1},FlatTerrain())
        self.assertEqual(len(changes),1)
        self.assertTrue(geo.validate_layout(g,refined))
        wrong=deepcopy(refined)
        wrong['cross_sections'][1]['elevation_ft'][2]-=1.
        self.assertFalse(geo.validate_layout(g,wrong))
        refined['cross_sections'][1]['reach_lengths_ft'][1]+=.1
        self.assertFalse(geo.validate_layout(g,refined))

    def test_subdivided_section_excluded_from_extension_and_infill(self):
        g=geometry()
        row=g['cross_sections'][2];row['ineffective_left']=[5.,108.]
        out,_,skips=geo.extend_ends(g,{r['rs']:111 for r in g['cross_sections']},FlatTerrain(),300,.30,True)
        self.assertEqual(row,out['cross_sections'][2])
        self.assertIn('SECTION_SPECIFIC_CONTROLS',{v['reason'] for v in skips})
        _,changes,_=geo.infill(g,{300.:1},FlatTerrain())
        self.assertEqual(changes,[])

    def test_recommendation_and_minimum_can_differ(self):
        m=dict(errors=0,critical=0,numerical=0,wet_ends=0,affected_locations=0,low_ends=0,warnings=13,max_wse_delta_ft=.01)
        narrow=dict(m,low_ends=1,warnings=12)
        self.assertLess(study.rank({'metrics':m}),study.rank({'metrics':narrow}))
        self.assertEqual(study.category(dict(text='Slope too steep for slope area to converge',code='NATIVE_UNCLASSIFIED_MESSAGE')),'NATIVE_SLOPE_AREA_FALLBACK')

    def test_missing_native_export_cannot_be_counted_as_zero(self):
        with patch.object(study,'verified_profiles'):
            with self.assertRaisesRegex(ValueError,'export required'):
                study.assessment({'hydraulics':{}}, {})

    def test_connectivity_window_clipped_to_raster_is_partial(self):
        from rasterio.transform import from_origin
        from ras_workflow import warning_paths
        g = geometry()
        row = g['cross_sections'][1]
        row['elevation_ft'][0] = 103
        terrain = FlatTerrain()
        terrain.source = {}
        terrain.transform = from_origin(321980, 4126290, 1, 1)
        terrain.z = np.full((40, 40), 100.)
        audit = dict(hdf={}, records=[dict(category='NATIVE_DIVIDED_FLOW',profile='Q',station='300')],
                     stages={'Q': {str(r['rs']): 105 for r in g['cross_sections']}})
        record = warning_paths.review(g, audit, terrain)['intervals'][0]
        self.assertEqual(record['tests']['100']['status'], 'PARTIAL_DEM')
        self.assertTrue(record['tests']['100']['at_stage'])

    def test_infill_does_not_invent_data_across_raster_void(self):
        terrain=FlatTerrain()
        terrain.sample=lambda x:np.full(len(x),np.nan)
        _,changes,skips=geo.infill(geometry(),{300.:1},terrain)
        self.assertEqual(changes,[])
        self.assertEqual(skips[0]['reason'],'SPACING_TERRAIN_OR_CHANNEL_ORDER')
