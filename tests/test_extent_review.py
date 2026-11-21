import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pyproj import Transformer

from ras_workflow.flood_edges import compare,read_lines
from ras_workflow.extent_review import aligned_stations
from ras_workflow.river import check_known_stages


class ExtentTests(unittest.TestCase):
    def test_recorded_preference_is_bound_to_a_common_station_and_appears_in_each_report(self):
        from docx import Document
        from ras_workflow import app_core as core,extent_review,report_decision
        from ras_workflow.common import ROOT
        m=dict(id='trial',revision=2,summary={'sha256':'current'},status='RESULTS_READY')
        cases=[dict(crs='EPSG:26910',run_id=name,rows=[{'rs':'100','center_xy':[0,y]}]) for name,y in [('first',0),('second',2)]]
        packet=dict(cases=cases,classification='NATIVE_GEOMETRY_COMPARISON',max_wse_change={'station':'100'})
        with tempfile.TemporaryDirectory(dir=ROOT/'status') as temp,patch.object(core,'BASE',Path(temp)), \
                patch.object(extent_review,'model_for',return_value=m),patch.object(extent_review,'selected_comparison',return_value=({},packet)):
            body=dict(decision='prefer_second',station='100',reason='Compare the surveyed banks')
            with self.assertRaisesRegex(ValueError,'common location'):extent_review.disposition('trial',body)
            cases[1]['rows'][0]['center_xy']=[0,0]
            decision=extent_review.disposition('trial',body)
            self.assertEqual(decision['preferred_run'],'second')
            self.assertEqual(decision['engineering_acceptance'],'NOT_ASSESSED')
            self.assertTrue(m['exports_need_refresh'])
            data=dict(summary={'hydraulics':{},'configuration':{}},river_checks={'extent_review':{'decision':decision}})
            for chinese in (False,True):
                doc=Document();report_decision.add(doc,data,chinese)
                output='\n'.join(p.text for p in doc.paragraphs)
                self.assertIn('RS 100 · second',output);self.assertIn(body['reason'],output)

    def setUp(self):
        self.transform=Transformer.from_crs(26910,4326,always_xy=True)
        self.cut=[[500000,5000000],[500100,5000000]]
        self.section={'rs':'100','wse_ft':400.,'map':{'cutline_xy':self.cut,
            'wet_segments_xy':[[[500020,5000000],[500085,5000000]]]}}
        self.center={'100':[500050,5000000]}

    def edges(self,xs):
        lines=[[self.transform.transform(500000+x,5000000+y) for y in (-6,6)] for x in xs]
        return read_lines('test.geojson',json.dumps(dict(type='MultiLineString',coordinates=lines)).encode())

    def test_shortfall_signed_and_search_units(self):
        result=compare(self.edges([-5,82]),'EPSG:26910',[self.section],self.center,10)
        self.assertEqual(result['matched'],1)
        row=result['rows'][0]
        self.assertAlmostEqual(row['left_shortfall_m'],25,places=2)
        self.assertAlmostEqual(row['right_shortfall_m'],-3,places=2)
        self.assertEqual(row['beyond_cut_m'],[5,0])

    def test_ambiguous_or_unseen_edges_do_not_score(self):
        for xs in ([10,40,88],[-9,82],[5,9]):
            r=compare(self.edges(xs),'EPSG:26910',[self.section],self.center,2.)
            self.assertEqual(r['matched'],0)
            self.assertIsNone(r['median_abs_m'])

    def test_require_same_physical_location(self):
        def case(x):
            return {'crs':'EPSG:26910','rows':[{'rs':'100','center_xy':[x,50]}]}
        self.assertEqual(aligned_stations([case(5),case(5.5)]),{'100'})
        self.assertEqual(aligned_stations([case(5),case(8)]),set())

    def test_native_subcritical_readback_never_downgraded(self):
        with self.assertRaisesRegex(ValueError,r'Dev at downstream RS 34913.*critical elevation 136.1513'):
            check_known_stages([{'id':'Dev'},{'id':'Holdout'}],'34913',[135.7398,138.3264],
                               [136.1513,138.3264],[136.1513,137.7383])
        check_known_stages([{'id':'Holdout'}],'34913',[138.32644],[138.3264])
