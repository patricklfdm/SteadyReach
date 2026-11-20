import unittest
from ras_workflow.feasibility import assess, scope


class FeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.model = dict(scenario='q100', model_type='river')
        self.config = dict(scenarios=[dict(id='q100', profiles=[dict(id='Q100', flow_cfs=457, source='study')])])

    def rows(self, geom, **kwargs):
        packet = assess(self.model,self.config,geom,kwargs.pop('answers',{}),**kwargs)
        return {r['key']:r for r in packet['rows']}

    def test_no_false_scope_decision_from_empty_map_and_dem(self):
        rows = self.rows({'channel_geometry_basis':'conditional_surface_dem'})
        self.assertEqual(rows['scope']['status'],'review')
        self.assertEqual(rows['bed']['status'],'conditional')
        self.assertEqual(rows['boundary']['status'],'missing')

    def test_mapped_junction_requires_review_even_when_user_expects_one_path(self):
        self.model['production_scope']={'flow_paths':'single'}
        rows = self.rows({},reach={'mapped_junctions':[dict(direction='entering')]})
        self.assertEqual(rows['scope']['status'],'review')
        self.model['production_scope']['flow_paths']='parallel'
        self.assertEqual(assess(self.model,self.config,{}, {})['state'],'outside')
        with self.assertRaises(ValueError):scope({'flow_paths':'explore'})

    def test_known_stage_per_profile_and_datum_conflict(self):
        self.model['metadata']={'dem_vertical_datum':'NGVD29'}
        geom=dict(vertical_datum='NAVD88',flow_regime='subcritical',
                  boundaries={'downstream':{'type':'known_stage','stages_ft':[0]}})
        rows=self.rows(geom)
        self.assertEqual(rows['datum']['status'],'conflict')
        self.assertEqual(rows['boundary']['status'],'review')
        geom['boundaries']['downstream']['stages_ft']=[0,1]
        self.assertEqual(self.rows(geom)['boundary']['status'],'missing')

    def test_invert_evidence_not_inherited_from_reported_dimensions(self):
        self.model['model_type']='culvert'
        geom={'structure':{'groups':[dict(shape='box',count=3,span_ft=8,rise_ft=6,
                                         length_ft=35,us_invert_ft=734.6,ds_invert_ft=734.1)]}}
        answers={'g.structure.groups.0.'+p:{'evidence_class':'reported','basis':'dimensioned photo'}
                 for p in ('shape','count','span_ft','rise_ft')}
        answers['g.structure.groups.0.us_invert_ft']={'evidence_class':'assumed','basis':'estimated from slope'}
        rows=self.rows(geom,answers=answers)
        self.assertEqual(rows['openings']['status'],'review')
        self.assertEqual(rows['inverts']['status'],'conditional')
        self.assertEqual(rows['inverts']['facts']['values'][1]['basis'],'estimated from slope')

    def test_discharge_at_gage_and_boundary_stage_are_independent(self):
        source={'attempts':[{'route':'USGS_boundary_records','status':'CANDIDATES','stations':[
            dict(station='11160000',name='Test gage',lonlat=[-122,37],distance_to_pin_m=0,
                 rating={'min_cfs':0,'max_cfs':100,'validity':[]})]}]}
        reach={'anchor_lonlat':[[-122,37.01],[-122,37.002]]}
        row=self.rows({},acquisition=source,reach=reach)['boundary']
        station=row['facts']['stations'][0]
        self.assertTrue(station['transfer_required'])
        self.assertGreater(station['boundary_m'],200)
        self.assertEqual(station['outside_rating'],['Q100'])
        self.assertEqual(row['status'],'missing')
        self.model['map_picks']={'river':[[0,0],[1,1]]}
        self.assertIsNone(self.rows({},acquisition=source,reach=reach)['boundary']['facts']['stations'][0]['boundary_m'])
        from pyproj import Transformer
        convert=Transformer.from_crs(4326,32610,always_xy=True)
        self.model['terrain']={'crs_wkt':'EPSG:32610'}
        self.model['map_picks']['river']=[convert.transform(-122,37.004),convert.transform(-122,37.001)]
        distance=self.rows({},acquisition=source,reach=reach)['boundary']['facts']['stations'][0]['boundary_m']
        self.assertAlmostEqual(distance,111,delta=1)
