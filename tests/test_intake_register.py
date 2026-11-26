import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest
from unittest.mock import patch

from pyproj import Transformer
from ras_workflow import intake_boundary as b
from ras_workflow.intake_register import outcome


class IntakeBoundary(unittest.TestCase):
    def setUp(self):
        self.event=dict(profile='Flood',event='Flood-A',date='2015-10-01',station='12345678')
        self.loc=lambda y:Transformer.from_crs(32610,4326,always_xy=True).transform(500000,y)
        x,y=self.loc(5000000)
        self.ctx=dict(profiles=[dict(id='Flood',flow_cfs=200)],geom=dict(flow_regime='subcritical',horizontal_crs='EPSG:32610',vertical_datum='NAVD88',cross_sections=[
            dict(rs=rs,center_xy=[500000,v],cutline_xy=[[499980,v],[500020,v]],station_ft=[0,130]) for rs,v in [(200,5000050),(100,5000000)]]))
        self.row=dict(profile='Flood',event='Flood-A',date='2015-10-01',role='boundary',kind='stage',x=x,y=y,horizontal_crs='EPSG:4326',elevation=51,
            unit='ft',vertical_datum='NAVD88',flow=200,flow_unit='cfs',vertical_uncertainty=.1,source='USGS-12345678 local survey')
        self.doc=dict(events=[self.event],observations=[(self.row,{'sha256':'original'})],stations={'12345678':dict(station='12345678',lonlat=[x,y],datum='NAVD88')},transfers=[])

    def result(self):return b.screen(self.ctx,self.doc)['rows'][0]

    def test_event_station_datum_flow_and_role(self):
        self.assertEqual(self.result()['stage_ft'],51)
        for field,value in [('event','other'),('date','2016-10-01'),('source','USGS-87654321'),('vertical_datum','NGVD29'),('flow',400),('role','holdout'),('vertical_uncertainty',None)]:
            with self.subTest(field=field),patch.dict(self.row,{field:value}):self.assertIsNone(self.result()['stage_ft'])
        self.doc['observations'].append((dict(self.row,elevation=53),{'sha256':'other'}))
        self.assertEqual(self.result()['status'],'CONFLICT')

    def test_direct_survey_outlet_requires_a_matching_independent_point(self):
        self.row.update(kind='boundary_stage',source='Survey A, row 12',vertical_uncertainty='')
        event=dict(profile='Flood',event='Flood-A',date='2015-10-01',method='direct_outlet_survey',
                   point_source=self.row['source'],unit='ft',horizontal_crs='EPSG:4326',vertical_datum='NAVD88',
                   source={'sha256':'independent-point'},accept_unquantified_for_screening=True,
                   native_point={k:self.row[k] for k in ('x','y','elevation')})
        self.doc['events']=[event]
        self.assertEqual(self.result()['status'],'CONDITIONAL_SURVEY')
        self.assertEqual(self.result()['issues'],['UNCERTAINTY_MISSING'])
        geom=dict(self.ctx['geom'],model_type='river',boundaries={'downstream':{'type':'known_stage','stages_ft':[51]}})
        model=dict(attachments=[{'path':'survey/observed_profiles.csv'}],production_scope={'purpose':'review'})
        with patch('ras_workflow.intake_register.context',return_value=self.ctx),patch.object(b,'documents',return_value=self.doc):
            self.assertEqual(b.controls_for_run(model,{},geom,[]),[])
            with patch.dict(model,production_scope={'purpose':'design'}):
                self.assertTrue(b.controls_for_run(model,{},geom,[]))
        for key,val in [('elevation',52),('x',-120.),('date','2014-10-01'),('vertical_datum','NGVD29'),
                        ('source','USGS-12345678'),('vertical_uncertainty','0'),('kind','gage_height')]:
            with self.subTest(key=key),patch.dict(self.row,{key:val}):
                self.assertEqual(self.result()['status'],'BLOCKED')
        with patch.dict(event,source={'sha256':'original'}):
            self.assertEqual(self.result()['status'],'BLOCKED')
        with patch.dict(self.row,vertical_uncertainty=.1),patch.dict(event,vertical_uncertainty=.1):
            self.assertEqual(self.result()['status'],'ELIGIBLE')
        x,y=self.loc(5000050)
        with patch.dict(self.row,x=x,y=y),patch.dict(event['native_point'],x=x,y=y):
            self.assertIn('DOCUMENTED_TRANSFER_REQUIRED',self.result()['issues'])

    def test_bound_transfer_is_event_specific(self):
        xy=self.loc(5000200);self.row.update(x=xy[0],y=xy[1]);self.doc['stations']['12345678']['lonlat']=xy
        self.assertIn('DOCUMENTED_TRANSFER_REQUIRED',self.result()['issues'])
        transfer=dict(self.event,target_rs='100',datum='NAVD88',offset_ft=-.75,uncertainty_ft=.25,basis='paired sections',source={'sha256':'paired'})
        self.doc['transfers']=[transfer];self.assertEqual(self.result()['stage_ft'],50.25)
        for k,v in [('target_rs','200'),('date','2017-04-01'),('source',{'sha256':'original'}),('uncertainty_ft',0)]:
            with self.subTest(field=k),patch.dict(transfer,{k:v}):self.assertIsNone(self.result()['stage_ft'])

    def test_renaming_station_datum_requires_documented_elevation_conversion(self):
        self.doc['stations']['12345678']['datum']='NGVD29'
        self.assertIn('DOCUMENTED_DATUM_TIE_REQUIRED',self.result()['issues'])
        tie=dict(self.event,from_datum='NGVD29',to_datum='NAVD88',basis='surveyed vertical tie',
                 source_stage_ft=48,offset_ft=3,uncertainty_ft=.2,source={'sha256':'conversion'})
        self.doc['datum_ties']=[tie]
        self.assertEqual(self.result()['stage_ft'],51)
        with patch.dict(tie,offset_ft=-3):self.assertIsNone(self.result()['stage_ft'])

    def test_gage_height_needs_dated_zero(self):
        self.row.update(kind='gage_height',gage_zero=100)
        self.assertIsNone(self.result()['stage_ft']);self.doc['gage_zeros']=[dict(self.event,datum='NAVD88',zero_ft=100)]
        self.assertEqual(self.result()['stage_ft'],151)

    def test_frozen_sources_survive_removal_and_detect_edits(self):
        from hashlib import sha256
        from ras_workflow import intake_freeze as freeze
        from ras_workflow.common import digest
        from ras_workflow.intake_register import inventory
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);original=folder/'survey.json';original.write_bytes(b'{"files":[]}')
            sha=sha256(original.read_bytes()).hexdigest()
            ref=dict(path='detached/survey.json',sha256=sha,role='survey_manifest')
            ctx=dict(schema='hydraulic_intake_v1',edition='detached',model_type='river',geom={},terrain={},fields=[],
                     attachments=[ref],sources=[ref],attempts=[],profiles=[],location={},products=[],original_tiles=[])
            register=inventory(ctx,lambda _:original)
            manifest=json.dumps(dict(context=ctx,register_hash=digest(register)))
            archive=folder/'snapshot.zip'
            with ZipFile(archive,'w') as z:
                z.writestr('intake.json',manifest);z.writestr('objects/'+sha,original.read_bytes())
            original.unlink()
            self.assertEqual(freeze.replay(archive)['register'],register)
            with ZipFile(archive,'w') as z:
                z.writestr('intake.json',manifest);z.writestr('objects/'+sha,b'{}')
            with self.assertRaisesRegex(ValueError,'changed'):freeze.replay(archive)

    def test_metadata_is_bound_to_an_original(self):
        from ras_workflow.intake_register import inventory
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);note=folder/'note.json'
            source=dict(path='file.pdf',sha256='a'*64,role='source_material')
            ref=dict(path='note.json',sha256='b'*64,role='source_metadata_note')
            ctx=dict(edition='test',model_type='river',geom={'vertical_datum':'NAVD88'},terrain={},fields=[],
                     attachments=[source],sources=[ref,source],notes=[ref],attempts=[],profiles=[],location={},products=[],original_tiles=[])
            note.write_text(json.dumps(dict(category='stage',date='2020-03-17',datum='NGVD29',source_sha256=source['sha256'])))
            stage=next(r for r in inventory(ctx,lambda _:note)['records'] if r['category']=='stage')
            self.assertEqual((stage['status'],stage['dates'],stage['conflicting_datums']),('CONFLICT',['2020-03-17'],['NGVD29']))
            ctx['sources']=[ref]
            with self.assertRaisesRegex(ValueError,'original'):inventory(ctx,lambda _:note)

    def test_search_outcomes(self):
        self.assertEqual([outcome(dict(status=s)) for s in ['NO_CATALOG_MATCH','NETWORK_FAILED','PARTIAL','CONFLICT','MATCH_CANDIDATE']],
                         ['EMPTY','UNAVAILABLE','PARTIAL','CONFLICT','FOUND'])

    def test_solver_gate_checks_declared_boundary(self):
        geom=dict(self.ctx['geom'],model_type='river',boundaries={'downstream':{'type':'known_stage','stages_ft':[51]}})
        m={'attachments':[{'path':'survey/observed_profiles.csv'}]}
        with patch('ras_workflow.intake_register.context',return_value=self.ctx),patch.object(b,'documents',return_value=self.doc):
            self.assertEqual(b.controls_for_run(m,{},geom,[]),[])
            self.row['date']='2010-02-03'
            self.assertEqual(b.controls_for_run(m,{},geom,[])[0]['code'],'UNSUPPORTED_GAGE_BOUNDARY')
