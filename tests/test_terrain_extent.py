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
from ras_workflow.common import ROOT, item, read, save


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


if __name__ == '__main__':
    unittest.main()
