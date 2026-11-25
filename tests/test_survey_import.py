import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ras_workflow import common, map_raster, native, survey_import


class SurveyImportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for module in (common, survey_import):
            mock = patch.object(module, 'ROOT', self.root)
            mock.start()
            self.addCleanup(mock.stop)
        with MemoryFile() as m:
            with m.open(driver='GTiff', crs='EPSG:32615', transform=from_origin(500000,4250100,2,2),
                        width=50,height=50,count=1,dtype='float32') as raster:
                raster.write(np.ones((50,50),dtype='float32'),1)
            self.dem = m.read()
        self.raw = {'field.tif':self.dem, 'field.txt':b'Test fixture only. Not a site survey.'}
        self.files = [dict(name=k,source='Test fixture',sha256=hashlib.sha256(v).hexdigest()) for k,v in self.raw.items()]
        lon,lat=Transformer.from_crs(32615,4326,always_xy=True).transform(500050,4250040)
        sections = []
        for i in range(4):
            y = 4250080 - i*20
            sections.append(dict(rs=(4-i)*100,center_xy=[500050,y],cutline_xy=[[500064,y],[500036,y]],
                                 station_ft=[0,20,40,60,80],elevation_ft=[12,10,8,10,12],bank_stations_ft=[20,60],
                                 reach_lengths_ft=[65,65,65] if i!=3 else [0,0,0],expansion_contraction=[.3,.1]))
        geom = dict(schema_version='1.0', model_type='river', river='Fixture',reach='Test',hydraulic_unit='international_ft',
                    vertical_datum='NAVD88',horizontal_crs='EPSG:32615',flow_regime='subcritical',
                    channel_geometry_basis='combined_survey_and_dem', cross_sections=sections,
                    boundaries={'downstream':dict(type='known_stage',stages_ft=[11])},
                    flowlines=[dict(id='river',xy=[s['center_xy'] for s in sections])])
        self.m = dict(schema_version='steadyreach_survey_1',location=dict(latitude=lat,longitude=lon),geometry=geom,
                      scenario=dict(id='field',channel_n=.03,overbank_n=.04,parameter_source='Explicit test assumption',
                                    profiles=[dict(id='Measured',flow_cfs=53.5,source='Test input')]),files=self.files,
                      terrain=dict(raster='field.tif',vertical_datum='NAVD88',vertical_unit='m'))

    def test_survey_start_reuses_verified_archived_image_without_dem_overrides(self):
        from ras_workflow import app_core, local_rasters
        with MemoryFile() as mem:
            with mem.open(driver='GTiff',crs='EPSG:32615',transform=from_origin(500000,4250100,2,2),
                          width=50,height=50,count=3,dtype='uint8') as ds:
                ds.write(np.ones((3,50,50),dtype='uint8'))
            image=mem.read()
        receipt=dict(schema_version='naip_acquisition_1.0',source='Fixture imagery',status='READY_FOR_MAP_REVIEW',
                     valid_fraction=1,raster=dict(sha256=hashlib.sha256(image).hexdigest()))
        def uploads():
            return [dict(name=k,content=base64.b64encode(v).decode())
                    for k,v in [('aerial.tif',image),('acquisition.json',json.dumps(receipt).encode())]]
        with patch.object(app_core,'BASE',self.root/'projects'),patch.object(app_core,'ROOT',self.root):
            model=app_core.create(dict(route='survey',title='Survey archive test',survey_files=self.upload(),local_rasters=uploads()))
        config=common.read(self.root/model['project'])
        self.assertEqual(config['terrain']['raster'],'survey/field.tif')
        self.assertEqual(config['delivery']['imagery']['raster'],'local_terrain/imagery.tif')
        loc=self.m['location']
        receipt['raster']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            local_rasters.validate(uploads(),None,None,loc['longitude'],loc['latitude'],imagery_only=True)

    def upload(self, manifest=None):
        data = dict(self.raw)
        data['survey.json'] = json.dumps(manifest or self.m).encode()
        return [dict(name=name,content=base64.b64encode(b).decode()) for name,b in data.items()]

    def test_install_and_recheck_full_source_inventory(self):
        pkg = survey_import.parse(self.upload())
        config = dict(location={})
        evidence = survey_import.install(self.root,config,pkg)
        model = dict(route='survey',attachments=evidence)
        self.assertEqual(evidence,survey_import.verified_sources(model))
        self.assertEqual(config['scenarios'],[self.m['scenario']])
        self.assertEqual(json.loads((self.root/config['geometry']).read_bytes())['provenance'],evidence)
        with self.assertRaisesRegex(ValueError,'inventory'):
            survey_import.verified_sources(dict(model,attachments=evidence[:-1]))
        (self.root/'survey'/'field.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'field.txt'):
            survey_import.verified_sources(model)

    def test_reject_inconsistent_inputs_before_persistence(self):
        for label,mutate in (
            ('missing source',lambda m:m['files'].pop()),
            ('incorrect hash',lambda m:m['files'][0].update(sha256='0'*64)),
            ('wrong vertical datum',lambda m:m['terrain'].update(vertical_datum='NGVD29')),
            ('unknown unit',lambda m:m['terrain'].update(vertical_unit='feet')),
            ('invalid CRS',lambda m:m['geometry'].update(horizontal_crs='EPSG:4326')),
            ('external input',lambda m:m['scenario'].update(native_project='unrelated.prj')),
            ('invalid roughness',lambda m:m['scenario'].update(channel_n=True)),
            ('unknown profile',lambda m:m['scenario']['profiles'][0].update(id='bad,name')),
            ('duplicate profile',lambda m:m['scenario']['profiles'].append(dict(m['scenario']['profiles'][0],id='mEasured'))),
            ('unusable sample',lambda m:m['geometry']['cross_sections'][0]['elevation_ft'].__setitem__(0,None)),
            ('unknown geometry key',lambda m:m['geometry'].update(approved_for_model=True)),
            ('missing cutline',lambda m:m['geometry']['cross_sections'][0].pop('cutline_xy')),
            ('outside raster',lambda m:m['location'].update(latitude=12)),
        ):
            with self.subTest(label=label):
                m=copy.deepcopy(self.m);mutate(m)
                with self.assertRaises(ValueError):
                    survey_import.parse(self.upload(m))
        for name in ('../field.tif','Geometry.Working.JSON','aux.txt','SURVEY.JSON'):
            rows=self.upload();rows[0]['name']=name
            with self.assertRaises(ValueError):survey_import.parse(rows)

    def test_write_manifest_with_citations_without_overwrite(self):
        data=dict(self.m);data.pop('files')
        definition=self.root/'definition.json';definition.write_text(json.dumps(data))
        sources=[]
        for n,b in self.raw.items():
            path=self.root/n;path.write_bytes(b);sources.append((path,'Test citation'))
        dest=survey_import.make_manifest(definition,sources)
        self.assertEqual(json.loads(dest.read_bytes())['files'][0]['sha256'],self.files[0]['sha256'])
        with self.assertRaises(FileExistsError):survey_import.make_manifest(definition,sources)

    def test_survey_wkt1_vs_wkt2_and_genuinely_different_datum(self):
        path=self.root/'raw.tif';path.write_bytes(self.dem)
        bounds=(500010,4250010,500080,4250080)
        r=map_raster.terrain(path,self.root/'same.tif','EPSG:32615',bounds,1,'NAVD88','m')
        self.assertEqual(r['valid_fraction'],1.)
        with self.assertRaisesRegex(ValueError,'different horizontal datums'):
            map_raster.terrain(path,self.root/'bad.tif','EPSG:26915',bounds,1,'NAVD88','m')

    def test_real_event_precision_in_eight_native_columns(self):
        for q,maximum in [(175/.3048**3,.001),(111/.3048**3,.001),(11300,0),(457,0),(.0123456,1e-6)]:
            field=native.discharge_field(q)
            self.assertEqual(len(field),8)
            self.assertLessEqual(abs(float(field)-q),maximum)
