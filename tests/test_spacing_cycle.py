"""Synthetic policy/geometry tests; actual native regression is recorded separately."""
import copy
import unittest
from types import SimpleNamespace
import numpy as np
from pyproj import CRS

from ras_workflow.spacing_cycle import policy, propose, nested, stop_reason
from ras_workflow.section_spacing import refine, intervals
from ras_workflow.terrain_auto import Sampler


def geometry_series():
    rows=[]
    for rs,y in [(400.,300.),(300.,200.),(200.,100.),(100.,0.)]:
        rows.append(dict(rs=rs,reach_id='river',center_xy=[0,y],cutline_xy=[[-50.,y],[50.,y]],
            station_ft=[0.,25.,50.,75.,100.],elevation_ft=[10.,5.,0.,5.,10.],bank_stations_ft=[25.,75.],
            reach_lengths_ft=[110.,100.,120.] if rs>100 else [0.,0.,0.],expansion_contraction=[.3,.1]))
    g=dict(model_type='river',horizontal_crs='EPSG:26913',vertical_datum='TEST',cross_sections=rows,
           flowlines=[dict(id='river',xy=[[0,300],[0,0]])])
    sampler=SimpleNamespace(crs=CRS.from_epsg(26913),datum='TEST',factor=1.,cell_ft=1.,unit='m',
        source=dict(path='synthetic',sha256='fixture'),sample=lambda p:np.abs(p[:,0])/5)
    sampler.stamp=lambda r:Sampler.stamp(sampler,r)
    for r in rows:sampler.stamp(r)
    first,_,targets=refine(g,intervals(g,[],'all'),sampler)
    second,_,_=refine(first,targets,sampler)
    return [g,first,second],sampler


class SpacingCycleTests(unittest.TestCase):
    def test_bounds_require_explicit_valid_policy(self):
        self.assertIsNone(policy({}))
        self.assertEqual(policy(dict(coverage_policy=dict(maximum_rounds=2,maximum_width_ft=2000))),
                         dict(maximum_rounds=2,maximum_width_ft=2000.))
        for rounds,width in [(0,2000),(4,2000),(True,2000),(1,float('nan')),(1,2100),(1,True)]:
            with self.assertRaises(ValueError):policy(dict(coverage_policy=dict(maximum_rounds=rounds,maximum_width_ft=width)))
        for malformed in (False,'yes',[],-1):
            with self.assertRaises(ValueError):policy(dict(coverage_policy=malformed))

    def test_shared_added_profile_extends_consistently_without_moving_banks_in_plan(self):
        geometries,sampler=geometry_series();original=copy.deepcopy(geometries)
        observations=[dict(rs=350,profile='Q100',left_excess_ft=2,right_excess_ft=2,wse_ft=12.),
                      dict(rs=350,profile='Q200',left_excess_ft=3,right_excess_ft=3,wse_ft=13.),
                      dict(rs=375,profile='Q100',left_excess_ft=1,right_excess_ft=1,wse_ft=11.)]
        result=propose(geometries,observations,sampler,200.)
        self.assertEqual(geometries,original);self.assertEqual(result['geometries'][0],original[0])
        self.assertEqual(result['water_levels_ft']['350.0'],13.)
        self.assertEqual({r['rs'] for r in result['changes']},{350.,375.})
        a=next(r for r in result['geometries'][1]['cross_sections'] if r['rs']==350)
        b=next(r for r in result['geometries'][2]['cross_sections'] if r['rs']==350)
        for field in ('station_ft','elevation_ft','cutline_xy','bank_stations_ft'):
            self.assertEqual(a[field],b[field])
        self.assertNotEqual(a['reach_lengths_ft'],b['reach_lengths_ft'])
        self.assertAlmostEqual(a['bank_stations_ft'][0]+a['cutline_xy'][0][0],-25.)
        nested(result['geometries'])

    def test_existing_wet_section_stays_protected(self):
        geometries,sampler=geometry_series()
        result=propose(geometries,[dict(rs=300,left_excess_ft=5,right_excess_ft=5,wse_ft=15.)],sampler,200.)
        self.assertEqual(result['geometries'],geometries)
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['retained_wet_sections'],[300.])
        self.assertTrue(result['unresolved'])

    def test_dem_failure_and_width_limit_return_no_mutation(self):
        for nodata in (True,False):
            geometries,sampler=geometry_series()
            if nodata:sampler.sample=lambda p:np.full(len(p),np.nan)
            result=propose(geometries,[dict(rs=350,left_excess_ft=20,right_excess_ft=20,wse_ft=30.)],sampler,120.)
            self.assertEqual(result['geometries'],geometries);self.assertFalse(result['changes'])

    def test_changed_shared_geometry_is_not_called_a_nested_correction(self):
        geometries,sampler=geometry_series()
        geometries[-1]['cross_sections'][2]['bank_stations_ft'][0]+=1
        with self.assertRaisesRegex(ValueError,'Original section changed'):
            propose(geometries,[],sampler,200.)

    def test_stops_distinguish_missing_compute_baseline_extent_and_round_bound(self):
        dry=dict(failed_cases=[],cases=[dict(wet_sections=[]),dict(wet_sections=[])])
        wet=dict(failed_cases=[],cases=[dict(wet_sections=[]),dict(wet_sections=[350])])
        limits=dict(maximum_rounds=2,maximum_width_ft=2000.)
        self.assertEqual(stop_reason(dry,{},0,limits),'COVERAGE_RESOLVED_REVIEW_REQUIRED')
        self.assertEqual(stop_reason(dict(dry,failed_cases=['refinement_1']),None,0,limits),'INCOMPLETE')
        self.assertEqual(stop_reason(dict(wet,cases=[dict(wet_sections=[300])]),{},0,limits),'BASELINE_COVERAGE_REVIEW')
        self.assertEqual(stop_reason(wet,dict(changes=[{}]),2,limits),'ROUND_LIMIT_REVIEW_REQUIRED')
        self.assertEqual(stop_reason(wet,dict(changes=[]),0,limits),'RETAINED_OR_GEOMETRY_REVIEW')
        self.assertIsNone(stop_reason(wet,dict(changes=[{}]),0,limits))


if __name__=='__main__':unittest.main()
