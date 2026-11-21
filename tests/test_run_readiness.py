from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_origin
from ras_workflow import run_readiness


class RunReadinessTests(TestCase):
    def setUp(self):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)
        for name,value in [('ras_workflow.native_session.require_exclusive',None),
                           ('ras_workflow.report_tools.discover',{'blocking_items':[]}),
                           ('ras_workflow.qgis_runtime.environment',None),
                           ('ras_workflow.common.ROOT',self.root)]:
            obj=patch(name,value) if isinstance(value,Path) else patch(name,return_value=value)
            obj.start()
            self.addCleanup(obj.stop)
        with rasterio.open(self.root/'terrain.tif','w',driver='GTiff',width=60,height=60,count=1,
                           dtype='float32',crs='EPSG:26910',transform=from_origin(400000,4900060,1,1)) as dst:
            dst.write(np.ones((60,60),dtype='float32'),1)
        self.config={'terrain':{'raster':'terrain.tif','vertical_unit':'m','vertical_datum':'NAVD88'}}
        self.geometry={'horizontal_crs':'EPSG:26910','vertical_datum':'NAVD88','cross_sections':[
            {'cutline_xy':[(400015,4900020),(400045,4900020)]},{'cutline_xy':[(400015,4900040),(400045,4900040)]}]}

    def check(self,mapped=True):
        return run_readiness.evaluate(self.root/'project.json',self.config,self.geometry,mapped,engine={'status':'READY'})

    def test_crop_matches_the_planned_square_and_leaves_no_derived_files(self):
        result=self.check()
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['gis']['terrain']['valid_fraction'],1)
        self.assertEqual(list(self.root.iterdir()),[self.root/'terrain.tif'])

    def test_gis_block_does_not_claim_solver_failure(self):
        self.geometry['horizontal_crs']='EPSG:32610'
        result=self.check()
        self.assertEqual(result['solver']['status'],'CHECKED')
        self.assertIn('different horizontal datums',result['gis']['issues'][0]['en'])
        self.assertEqual(self.check(False)['gis']['status'],'NOT_REQUESTED')

    def test_extent_coverage_and_missing_native_cutlines(self):
        self.geometry['cross_sections'][0]['cutline_xy'][0]=(399950,4900020)
        self.assertIn('covers only',self.check()['gis']['issues'][0]['en'])
        self.geometry['cross_sections']=[]
        self.assertEqual(self.check()['gis']['status'],'EXTENT_PENDING')

    def test_another_live_task_leaves_run_confirmation_untouched(self):
        from ras_workflow import app_core
        from ras_workflow.common import save
        save(self.root/'status/app/active.json',{'record':'previous.json'})
        save(self.root/'previous.json',{'status':'RUNNING'})
        with patch.object(app_core,'ROOT',self.root), patch.object(app_core,'model',return_value={'revision':1}), \
             patch.object(app_core,'require_idle'), patch.object(app_core,'task_alive',return_value=True), \
             patch('ras_workflow.app_parameters.confirm') as confirm:
            with self.assertRaisesRegex(ValueError,'Another project'):
                app_core.start('new',dict(start=True,confirmed=True,revision=1,review_token='current'))
            confirm.assert_not_called()
