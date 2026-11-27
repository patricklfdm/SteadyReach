"""The frozen original, mark coordinates and declared role have separate meanings."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ras_workflow import flood_marks as marks, flood_register as register
from ras_workflow.common import ROOT, read


class FloodEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.geometry = dict(crs='EPSG:3857',datum='NAVD88',paths=[[[0,0],[0,1000]]],
                             cuts=[dict(rs=100,xy=[[-30,0],[30,0]]),dict(rs=200,xy=[[-30,1000],[30,1000]])])
        self.row=dict(id=7,event_id=42,site_number='A',waterbody='Example River',longitude_dd=0.0,
                      latitude_dd=0.0001,site_latitude=70,site_longitude=60,vertical_datum_name='NGVD29',
                      elev_ft=42.2,site_description='USGS streamgage 12345678, downstream HWMs')
        self.raw=json.dumps([self.row,dict(self.row,id=8,site_number='B')]).encode()
        self.catalog=b'[{"id":42,"start_date":"2017-12-20","end_date":"2018-01-03","name":"Winter flood"}]'

    def test_locates_mark_instead_of_site_and_preserves_distinct_originals(self):
        p=marks.screen([(42,self.raw)],self.geometry,'EXAMPLE River')
        self.assertEqual(len(p['rows']),2)
        self.assertEqual(p['location_groups'],1)
        self.assertEqual([r['line'] for r in p['rows']],[1,2])
        for r in p['rows']:
            self.assertEqual(r['side'],'downstream')
            self.assertEqual(r['referenced_gage'],'12345678')
            self.assertEqual(r['suggestion'],'review_outlet_crossing')
            self.assertFalse(r['datum_matches'])
        with self.assertRaisesRegex(ValueError,'different event'):
            marks.screen([(41,self.raw)],self.geometry,'Example River')

    def test_frozen_replay_rejects_source_change(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp)
            v=register.freeze(folder,self.geometry,'Example River',self.catalog,'2018',[42],lambda _:self.raw)
            with patch.object(marks,'fetch',side_effect=AssertionError('network during replay')):
                p=register.replay(folder,v)
            self.assertEqual(p['rows'][0]['role'],'unresolved')
            self.assertNotIn('z_ft',p['rows'][0])
            with self.assertRaisesRegex(ValueError,'current project|Reopen|location'):
                with patch.object(register.core,'model',return_value=dict(id='test',revision=3)),patch.object(register.core,'folder',return_value=folder.parent),patch.object(register.core,'require_idle'):
                    register.action('test',{'revision':2},'roles')
            (folder/v/'event_42.json').write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError,'changed'):
                register.replay(folder,v)

    def test_failed_query_keeps_previous_freeze(self):
        with TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp)
            register.freeze(folder,self.geometry,'Example River',self.catalog,'2018',[42],lambda _:self.raw)
            previous=read(folder/'latest.json')
            with self.assertRaisesRegex(ValueError,'different event'):
                register.freeze(folder,self.geometry,'Example River',self.catalog,'2018',[42],lambda _:b'[{"event_id":100}]')
            self.assertEqual(read(folder/'latest.json'),previous)
