import unittest

import numpy as np
from pyproj import Transformer

from ras_workflow import california_flow, public_reach, river_boundary


class MappedReachTests(unittest.TestCase):
    def setUp(self):
        fwd=Transformer.from_crs(4326,32610,always_xy=True)
        self.origin=np.array(fwd.transform(-122,37))
        self.reverse=Transformer.from_crs(32610,4326,always_xy=True)
        def feature(xy,**attrs):
            coords=[self.reverse.transform(*(self.origin+p)) for p in xy]
            return dict(attributes=attrs,geometry=dict(paths=[coords]))
        self.river=[feature([(0,0),(200,12),(400,0),(600,0),(800,0)],gnis_name='Test Creek',
                            flowdir=1,permanent_identifier='hydro-a')]
        self.roads=[feature([(v,-40),(v,40)],NAME=name) for v,name in [(100,'Upper'),(400,'Middle'),(700,'Lower')]]

    def reach(self,x):
        lon,lat=self.reverse.transform(*(self.origin+[x,0]))
        return public_reach.propose(lat,lon,self.river,self.roads)

    def test_unnamed_leaving_branch_on_selected_reach_is_reported(self):
        coords=[self.reverse.transform(*(self.origin+p)) for p in [[200,12],[230,80]]]
        self.river.append(dict(attributes=dict(gnis_name=None,flowdir=1,permanent_identifier='side'),
                               geometry={'paths':[coords]}))
        result=self.reach(240)
        self.assertEqual([(p['source_id'],p['direction']) for p in result['mapped_junctions']],[('side','leaving')])
        self.assertEqual(self.reach(550)['mapped_junctions'],[])

    def test_pin_in_reach_supplies_ordered_endpoints_bends_and_crop(self):
        reach=self.reach(240)
        self.assertEqual((reach['upstream_crossing'],reach['downstream_crossing']),('Upper','Middle'))
        self.assertGreater(len(reach['anchor_lonlat']),2)
        self.assertGreaterEqual(reach['buffer_m'],300)
        self.assertGreater(reach['anchor_lonlat'][-1][0],reach['anchor_lonlat'][0][0])

    def test_pin_on_crossing_proposes_both_named_reaches(self):
        result=self.reach(400)
        self.assertEqual(result['status'],'CHOOSE_REACH')
        self.assertEqual([(v['upstream_crossing'],v['downstream_crossing']) for v in result['options']],
                         [('Upper','Middle'),('Middle','Lower')])

    def test_cannot_infer_direction_or_silently_skip_missing_crossing(self):
        with self.assertRaisesRegex(ValueError,'bracket'):self.reach(750)
        self.river[0]['attributes']['flowdir']=0
        with self.assertRaisesRegex(ValueError,'directed'):self.reach(240)

    def test_flow_provenance_reaches_native_configuration_and_preserves_explicit_source(self):
        from ras_workflow import app_autoprepare,app_core
        prefix='c.scenarios.0.profiles.0.'
        answer={'value':13000.,'evidence_class':'assumed','basis':'USGS Table 4; conditional transfer','candidate_record':{'cell':'T281'}}
        field={'key':prefix+'source','value':app_core.USER_SOURCE}
        self.assertEqual(app_autoprepare.source_label(field,{prefix+'flow_cfs':answer}),answer['basis'])
        self.assertIsNone(app_autoprepare.source_label(dict(field,value='Explicit field report'),{prefix+'flow_cfs':answer}))
        other={'key':'c.scenarios.0.parameter_source','value':app_core.USER_SOURCE}
        labels=app_autoprepare.source_label(other,{'c.scenarios.0.channel_n':answer})
        self.assertIn('channel_n (assumed)',labels)

    def test_station_matching_excludes_named_tributaries_and_diversions(self):
        for name in ('SOQUEL C AT SOQUEL CA','Soquel Creek near Soquel','Soquel Creek'):
            self.assertTrue(california_flow.station_on_river(name,'Soquel Creek'))
        self.assertTrue(california_flow.station_on_river('MERCED R A HAPPY ISLES BRIDGE NR YOSEMITE CA','Merced River'))
        for name in ('Soquel Creek Tributary at Soquel','Soquel Creek Canal near Soquel','East Soquel Creek'):
            self.assertFalse(california_flow.station_on_river(name,'Soquel Creek'))
        with self.assertRaisesRegex(ValueError,'workbook'):
            california_flow.table_value(b'Not a workbook','11160000')

    def test_robust_slope_keeps_adverse_and_flat_reaches_unavailable(self):
        rows=[dict(rs=17-i,center_xy=[80*i,0],height=20-.14*i+(.16 if i%4==0 else 0)) for i in range(17)]
        distance=lambda a,b:abs(a[0]-b[0])
        result=river_boundary.trend(rows,'downstream',lambda r:r['height'],distance)
        self.assertTrue(result['range'][0]<=result['slope']<=result['range'][1])
        self.assertGreaterEqual(sum(w['supported'] for w in result['windows']),2)
        for sign in (0,-1):
            self.assertIsNone(river_boundary.trend(rows,'downstream',lambda r:sign*r['height'],distance))
