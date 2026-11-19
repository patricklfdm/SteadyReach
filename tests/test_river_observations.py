import csv
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from ras_workflow import river_observations as obs


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.geometry={'horizontal_crs':'EPSG:26910','vertical_datum':'NAVD88','cross_sections':[
            {'rs':200,'cutline_xy':[[0,30],[30,30]],'station_ft':[0,100]},
            {'rs':100,'cutline_xy':[[0,0],[30,0]],'station_ft':[0,100]}]}
        self.summary={'hydraulics':{'profiles':[{'profile_id':'Observed','flow_cfs':40.0}]}}
        self.event=dict(event='E',date='2000-01-01',profile='Observed',downstream_ft=18.)
        self.row=dict(event='E',date='2000-01-01',role='holdout',kind='stage',x='10',y='30',horizontal_crs='EPSG:26910',
                      elevation='17',unit='ft',vertical_datum='NAVD1988',gage_zero='',flow='40',flow_unit='cfs',
                      vertical_uncertainty='0.1',horizontal_uncertainty_m='1',source='software-only fixture')
        raw=[dict(profile='Observed',rs=rs,station_ft=[0,100],elevation_ft=[9,12],wse_ft=18.) for rs in [200,100]]
        for p in [patch.object(obs,'bound_inputs',return_value=(None,self.geometry,None)),patch.object(obs,'native_rows',return_value=raw)]:
            p.start();self.addCleanup(p.stop)

    def screen(self,event=None,**changes):
        return obs.screen([dict(self.row,**changes)],self.summary,event)[0]

    def test_matched_flood_and_heldout(self):
        self.assertEqual(self.screen(self.event)['residual_ft'],1.)
        self.assertIsNone(self.screen()['residual_ft'])
        self.assertIsNone(self.screen(self.event,date='2001-05-02')['residual_ft'])
        self.assertIn('EVENT_DISCHARGE_MISMATCH',self.screen(self.event,flow='38')['issues'])

    def test_boundary_does_not_validate_itself(self):
        self.assertIsNone(self.screen(self.event,kind='boundary_stage',role='boundary',y='0')['residual_ft'])
        self.assertIn('DOWNSTREAM_STAGE_USED_AS_BOUNDARY',self.screen(self.event,y='0')['issues'])
        self.assertIn('BOUNDARY_REQUIRES_DOWNSTREAM_OBSERVATION',self.screen(self.event,kind='boundary_stage',role='boundary')['issues'])

    def test_surveyed_bed_interpolates_at_the_observed_point(self):
        result=self.screen(kind='bed',flow='',elevation='3.048',unit='m')
        self.assertAlmostEqual(result['model_ft'],10.)
        self.assertAlmostEqual(result['residual_ft'],0.)

    def test_gage_zero_datum_and_coordinates(self):
        self.assertIsNone(self.screen(self.event,kind='gage_height')['observed_ft'])
        self.assertEqual(self.screen(self.event,kind='gage_height',gage_zero='1')['residual_ft'],0.)
        self.assertIn('VERTICAL_DATUM_MISMATCH',self.screen(self.event,vertical_datum='NGVD29')['issues'])
        row=self.screen(self.event,y='100',horizontal_uncertainty_m='15')
        self.assertIn('OUTSIDE_SECTION_TOLERANCE',row['issues'])
        self.assertIn('POSITION_UNCERTAINTY_TOO_LARGE',row['issues'])
        self.assertIsNone(row['residual_ft'])

    def test_context_and_conflicting_point_do_not_create_independent_residuals(self):
        self.assertIsNone(self.screen(self.event,role='context')['residual_ft'])
        self.geometry['cross_sections'][1]['cutline_xy']=[[0,31],[30,31]]
        row=self.screen(self.event)
        self.assertIn('MULTIPLE_NEARBY_SECTIONS',row['issues'])
        self.assertIsNone(row['residual_ft'])

    def test_template_and_malformed_csv(self):
        header=(Path(obs.__file__).parent/'templates/observation-template.csv').read_text().strip()
        self.assertEqual(tuple(header.split(',')),obs.COLUMNS)
        buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=obs.COLUMNS);w.writeheader();w.writerow(self.row)
        self.assertEqual(obs.parse('\ufeff'+buf.getvalue()),[self.row])
        for text in (header,header+',source\n',header+'\nx,1',buf.getvalue().rstrip()+',extra'):
            with self.assertRaises(ValueError):obs.parse(text)
