"""Coverage planning is bounded; cached expansion never changes saved engineering inputs."""
import copy
import unittest
from unittest.mock import patch

from pyproj import Transformer

from ras_workflow import terrain_extent_auto as auto, app_terrain_extent


class AutomaticExtentTests(unittest.TestCase):
    def setUp(self):
        self.x,self.y=Transformer.from_crs(4326,26913,always_xy=True).transform(-107,37)
        self.model=dict(model_type='river',map_picks=dict(river=[[self.x-100,self.y],[self.x+100,self.y]]))
        self.geometry=dict(cross_sections=[],horizontal_crs='EPSG:26913')
        self.config=dict(location=dict(latitude=37,longitude=-107))
        self.info=dict(crs='EPSG:26913',bounds=[self.x-50,self.y-50,self.x+50,self.y+50],resolution=[1,1])

    def test_radius_covers_full_reach_and_requested_width(self):
        result=auto.plan(self.model,self.geometry,self.config,self.info)
        self.assertEqual(result['status'],'EXPANSION_NEEDED')
        self.assertGreaterEqual(result['buffer_m'],250)
        self.assertLessEqual(result['buffer_m'],2000)
        self.assertEqual(result['new_download_bytes'],0)
        self.assertFalse(result['geometry_changed'])
        self.assertAlmostEqual(result['padding_native_units'],440*.3048+2)

    def test_existing_coverage_needs_no_mutation(self):
        self.info['bounds']=[self.x-1000,self.y-1000,self.x+1000,self.y+1000]
        self.assertEqual(auto.plan(self.model,self.geometry,self.config,self.info)['status'],'ALREADY_COVERED')

    def test_no_explicit_reach_does_not_guess_one(self):
        self.model['map_picks']={}
        self.assertEqual(auto.plan(self.model,self.geometry,self.config,self.info)['status'],'NO_EXPLICIT_EXTENT')

    def test_qa_covers_asymmetric_extension_of_existing_cutlines(self):
        self.geometry['cross_sections']=[dict(cutline_xy=[[self.x-200,self.y],[self.x+200,self.y]])]
        result=auto.plan(self.model,self.geometry,self.config,self.info,1200)
        self.assertAlmostEqual(result['required_bounds'][0],self.x-200-1200*.3048-2)

    def test_projected_feet_are_converted_as_units_not_meters(self):
        self.info.update(crs='EPSG:2232',bounds=[0,0,1,1])
        self.model['map_picks']['river']=[[2000000,1000000],[2000100,1000000]]
        result=auto.plan(self.model,self.geometry,self.config,self.info)
        self.assertAlmostEqual(result['padding_native_units'],440*.3048/(1200/3937)+2)

    def test_large_or_high_resolution_requests_stop_before_allocation(self):
        self.model['map_picks']['river'][0][0]-=10000
        self.assertEqual(auto.plan(self.model,self.geometry,self.config,self.info)['reason'],'AUTOMATIC_RADIUS_LIMIT')
        self.setUp()
        self.info['resolution']=[.01,.01]
        self.assertEqual(auto.plan(self.model,self.geometry,self.config,self.info)['reason'],'AUTOMATIC_CELL_LIMIT')

    def test_invalid_geometry_is_not_reinterpreted(self):
        self.geometry['cross_sections']=[dict(cutline_xy=[[0,0],[1,1]])]
        self.geometry['horizontal_crs']='EPSG:26911'
        with self.assertRaisesRegex(ValueError,'coordinates differ'):
            auto.plan(self.model,self.geometry,self.config,self.info)
        for width in (True,None,float('nan'),2001):
            with self.subTest(width=width),self.assertRaises(ValueError):
                auto.plan(self.model,self.geometry,self.config,self.info,width)

    def test_worker_uses_internal_transaction_and_records_preserved_cells(self):
        m=dict(self.model,session='test.json',terrain=dict(raster=dict(sha256='old')),revision=3)
        context=(None,None,None,None,self.config,self.geometry,None,dict(raster=dict(sha256='old',role='artifact')),self.info)
        with patch('ras_workflow.geometry_editor.context',return_value=context),patch.object(app_terrain_extent,'expand_model',return_value=dict(terrain=dict(raster=dict(sha256='new')))) as expand:
            result=auto.ensure(m)
        self.assertEqual(result['status'],'EXPANDED')
        self.assertTrue(result['old_cells_preserved'])
        self.assertEqual(expand.call_args.kwargs['maximum_cells'],16_000_000)

    def test_missing_cached_tiles_preserve_original_model_and_return_action(self):
        m=dict(self.model,session='test.json',terrain=dict(raster=dict(sha256='old')),revision=3)
        before=copy.deepcopy(m)
        context=(None,None,None,None,self.config,self.geometry,None,dict(raster=dict(sha256='old')),self.info)
        with patch('ras_workflow.geometry_editor.context',return_value=context),patch.object(app_terrain_extent,'expand_model',side_effect=ValueError('Cached originals do not fully cover')):
            result=auto.ensure(m)
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertEqual(result['new_download_bytes'],0)
        self.assertEqual(m,before)


if __name__=='__main__':
    unittest.main()
