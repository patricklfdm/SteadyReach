"""Cached coverage expansion regressions using synthetic raster cells."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from ras_workflow import app_core, app_geometry, app_terrain_extent, geometry_editor, intake
from ras_workflow.common import ROOT, digest, item, read, save


class TerrainExtentTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'status').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='test_extent_', dir=ROOT / 'status')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.x, self.y = Transformer.from_crs(4326, 26913, always_xy=True).transform(-107., 37.)
        self.source = self.folder / 'synthetic_source.tif'
        self.old = self.folder / 'synthetic_working.tif'
        self.cells = np.arange(160000, dtype='float32').reshape(400, 400)
        self.write(self.source, self.cells, from_origin(self.x-200, self.y+200, 1, 1))
        self.old_cells = self.cells[150:250, 150:250] + .125
        self.write(self.old, self.old_cells, from_origin(self.x-50, self.y+50, 1, 1))
        self.previous = dict(raster=item(self.old), products=[dict(source=item(self.source))])
        self.configuration = dict(location=dict(latitude=37., longitude=-107.))

    def write(self, path, values, transform):
        with rasterio.open(path, 'w', driver='GTiff', width=values.shape[1], height=values.shape[0],
                           count=1, dtype='float32', crs='EPSG:26913', transform=transform, nodata=np.nan) as out:
            out.write(values, 1)

    def test_expansion_preserves_every_old_cell_and_grid(self):
        result = app_terrain_extent.expand_cached(self.previous, self.configuration, 100., self.folder/'expanded')
        with rasterio.open(ROOT/result['raster']['path']) as out, rasterio.open(self.old) as old:
            col, row = (~out.transform) * (old.transform.c, old.transform.f)
            np.testing.assert_array_equal(out.read(1)[round(row):round(row)+100, round(col):round(col)+100], self.old_cells)
            self.assertEqual(out.res, old.res)
            self.assertTrue(np.isfinite(out.read(1)).all())
        self.assertEqual(result['expansion']['new_download_bytes'], 0)

    def test_missing_coverage_does_not_write_a_working_raster(self):
        destination = self.folder/'too_large'
        with self.assertRaisesRegex(ValueError, 'do not fully cover'):
            app_terrain_extent.expand_cached(self.previous, self.configuration, 500., destination)
        self.assertFalse((destination/'terrain_aoi.tif').exists())

    def test_automatic_cell_limit_rejects_before_output(self):
        destination=self.folder/'over_budget'
        with self.assertRaisesRegex(ValueError,'cell limit'):
            app_terrain_extent.expand_cached(self.previous,self.configuration,100.,destination,maximum_cells=100)
        self.assertFalse(destination.exists())

    def test_rebinding_preserves_samples_banks_and_old_evidence(self):
        row=dict(cutline_xy=[[self.x-20,self.y],[self.x+20,self.y]],center_xy=[self.x,self.y],
                 station_ft=[0,20,40],elevation_ft=[3,1,4],bank_stations_ft=[10,30])
        row['terrain_sampling']=dict(raster=self.previous['raster'],vertical_unit='m',vertical_datum='TEST',
            spatial_fingerprint=digest({k:row[k] for k in ('cutline_xy','station_ft','elevation_ft','center_xy')}))
        changed=copy.deepcopy(row);changed['elevation_ft'][1]=2
        other=copy.deepcopy(row);other['terrain_sampling']['raster']=dict(sha256='other')
        geometry=dict(cross_sections=[row,changed,other],horizontal_crs='EPSG:26913');before=copy.deepcopy(geometry)
        updated,indices=app_terrain_extent.rebind_preserved_sections(geometry,self.previous,dict(raster=dict(sha256='expanded')),'m','TEST')
        self.assertEqual(indices,[0]);self.assertEqual(geometry,before)
        for key in ('cutline_xy','station_ft','elevation_ft','center_xy','bank_stations_ft'):
            self.assertEqual(updated['cross_sections'][0][key],row[key])
        self.assertEqual(updated['cross_sections'][0]['previous_terrain_sampling'],[row['terrain_sampling']])
        self.assertEqual(updated['cross_sections'][1:],geometry['cross_sections'][1:])

    def test_invalid_and_unchanged_extents_are_rejected(self):
        for radius in (None, True, float('nan'), 0, 5001):
            with self.subTest(radius=radius), self.assertRaises(ValueError):
                app_terrain_extent.expand_cached(self.previous, self.configuration, radius, self.folder/'invalid')
        result = app_terrain_extent.expand_cached(self.previous, self.configuration, 100., self.folder/'expanded')
        with self.assertRaisesRegex(ValueError, 'already covers'):
            app_terrain_extent.expand_cached(result, self.configuration, 50., self.folder/'repeat')

    def test_geometry_action_preserves_answers_metadata_and_picks(self):
        with patch.object(app_core, 'BASE', self.folder/'projects'):
            model = app_core.create(dict(title='Synthetic expansion test', latitude=37., longitude=-107.,
                                        route='coordinates', model_type='river'))
            session = intake.prepare(ROOT/model['project'], 'q100')
            model.update(session=session['session'], terrain=self.previous, status='INPUTS_READY',
                         metadata=dict(dem_vertical_unit='m', dem_vertical_datum='TEST_DATUM'),
                         map_picks=dict(river=[[self.x, self.y]]))
            app_core.persist(model)
            sp = ROOT/model['session']
            save(sp.parent/'terrain_checkpoint.json', dict(terrain=self.previous, metadata=dict(products=[])))
            draft = read(sp.parent/'draft.json')
            draft['answers']['c.scenarios.0.profiles.0.flow_cfs'] = dict(value=100., evidence_class='assumed')
            save(sp.parent/'draft.json', draft)
            before = copy.deepcopy(draft)
            result = app_geometry.perform(model['id'], 'expand-terrain', dict(revision=0, buffer_m=100.))
            after = read(sp.parent/'draft.json')
            self.assertEqual(after['answers'], before['answers'])
            self.assertEqual(after['geometry'], before['geometry'])
            self.assertEqual(result['metadata'], model['metadata'])
            self.assertEqual(result['map_picks'], model['map_picks'])
            self.assertEqual(geometry_editor.context(sp)[7]['raster']['sha256'], result['terrain']['raster']['sha256'])
            with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                app_geometry.perform(model['id'], 'expand-terrain', dict(revision=0, buffer_m=150.))

    def local_revision(self):
        model=app_core.create(dict(title='Synthetic local revision',latitude=37.,longitude=-107.,route='coordinates',model_type='river'))
        config=read(ROOT/model['project']);save(self.folder/'terrain.json',self.previous)
        config['terrain']=dict(mode='local',raster=str(self.old),provenance=str(self.folder/'terrain.json'),vertical_unit='m',vertical_datum='TEST_DATUM',create_native=False)
        save(ROOT/model['project'],config)
        session=intake.prepare(ROOT/model['project'],'q100')
        model.update(session=session['session'],terrain=self.previous,status='INPUTS_READY',metadata=dict(dem_vertical_unit='m',dem_vertical_datum='TEST_DATUM'))
        app_core.persist(model)
        return model,ROOT/model['session']

    def test_local_revision_without_acquisition_checkpoint_can_expand(self):
        with patch.object(app_core,'BASE',self.folder/'projects'):
            model,sp=self.local_revision();before=read(sp.parent/'draft.json')
            self.assertFalse((sp.parent/'terrain_checkpoint.json').exists())
            result=app_terrain_extent.expand_model(model,dict(revision=0,buffer_m=100.))
            after=read(sp.parent/'draft.json');checkpoint=read(sp.parent/'terrain_checkpoint.json')
            self.assertEqual(after['geometry'],before['geometry']);self.assertEqual(after['answers'],before['answers'])
            self.assertEqual(result['metadata'],model['metadata'])
            self.assertEqual(digest(checkpoint['terrain']),digest(result['terrain']));self.assertNotIn('metadata',checkpoint)
            self.assertEqual(geometry_editor.context(sp)[7]['raster']['sha256'],result['terrain']['raster']['sha256'])

    def test_failed_commit_restores_absent_checkpoint_and_original_draft(self):
        with patch.object(app_core,'BASE',self.folder/'projects'):
            model,sp=self.local_revision();before=read(sp.parent/'draft.json')
            with patch.object(app_core,'persist',side_effect=OSError('test commit failure')):
                with self.assertRaisesRegex(OSError,'test commit failure'):
                    app_terrain_extent.expand_model(model,dict(revision=0,buffer_m=100.))
            self.assertFalse((sp.parent/'terrain_checkpoint.json').exists())
            self.assertEqual(read(sp.parent/'draft.json'),before)
            self.assertEqual(read(app_core.folder(model['id'])/'app.json'),model)


if __name__ == '__main__':
    unittest.main()
