"""Review rules use controlled inputs here. Field-case checks use the retained native results."""
from unittest import TestCase

import numpy as np

from ras_workflow.floodplain_path import corridor, line_surface
from ras_workflow.result_assessment import event_tailwaters, finding, next_actions
from ras_workflow.review_evidence import boundary_evidence, rating
from ras_workflow.river_observations import holdout_stages
from ras_workflow.section_context import flow_path_flags


class Terrain:
    cell_ft = factor = 1.
    def __init__(self, heights):
        self.sample = heights


class OverbankTests(TestCase):
    flat = Terrain(lambda xy: np.zeros(len(xy)))

    def cut(self, y):
        return dict(cutline_xy=[[0., y],[10., y]], station_ft=[0.,10.], bank_stations_ft=[4.,6.])

    def screen(self, sampler, neighbor=None):
        return corridor(self.cut(0), neighbor or self.cut(4), 0, sampler, [1., 2.], 0, within_cuts=True)

    def test_slope_ridge_and_missing_strip(self):
        self.assertTrue(self.screen(self.flat)['at_lower_stage'])
        def ridge(z):
            return Terrain(lambda xy: np.where(xy[:,1]==2, z, 0.))
        self.assertEqual(self.screen(ridge(3.))['status'],'NO_CONNECTED_LOW_ROUTE_IN_STRIP')
        self.assertEqual(self.screen(ridge(1.4))['status'],'STAGE_DEPENDENT_LOW_ROUTE')
        self.assertEqual(self.screen(ridge(np.nan))['status'],'INCOMPLETE_DEM')

    def test_folded_or_bent_cut_abstains(self):
        other = self.cut(4)
        other['cutline_xy'] = [[5.,-4.],[5.,8.]]
        self.assertEqual(self.screen(self.flat,other)['status'],'AMBIGUOUS_CORRIDOR')
        other['cutline_xy'] = [[0.,4.],[5.,6.],[10.,4.]]
        self.assertEqual(self.screen(self.flat,other)['status'],'BENT_CUT_REVIEW')

    def test_surface_is_clipped_to_road_inside_strip_in_either_direction(self):
        corners=[[0,0],[4,0],[4,4],[0,4]]
        road=[[-30,2],[30,2]]
        for ring in [corners,corners[::-1]]:
            surface=line_surface(road,ring,Terrain(lambda xy: np.where(xy[:,0]==2,np.nan,xy[:,0])))
            self.assertEqual(surface,dict(status='INCOMPLETE_DEM',range_ft=[0.,4.],samples=5,missing=1))
            self.assertIsNone(line_surface([[-1,-1],[1,-1]],ring,self.flat))
        self.assertEqual(line_surface(road,corners,Terrain(lambda xy: np.full(len(xy),np.nan)))['range_ft'],None)

    def test_diagnostic_distinguishes_exchange_from_unresolved_geometry(self):
        diag=self.screen(self.flat)
        self.assertEqual(flow_path_flags(diag,40,60,[{}]),
                         ['ABRUPT_PARTITION','REVIEW_LATERAL_EXCHANGE','VERIFY_CROSSING_OPENINGS'])
        self.assertEqual(flow_path_flags(dict(status='AMBIGUOUS_CORRIDOR'),40,.5,[]),
                         ['ABRUPT_PARTITION','REVIEW_SECTION_ALIGNMENT'])
        self.assertEqual(flow_path_flags(diag,2,3,[]),[])
        self.assertEqual(flow_path_flags(diag,None,3,[]),['SHARE_UNAVAILABLE'])


class ApplicabilityTests(TestCase):
    sample=(b'# //STATION AGENCY="USGS " NUMBER="12345678 "\n'
            b'# //RATING_INDEP PARAMETER="Gage height (ft)"\n'
            b'# //RATING_DEP PARAMETER="Discharge (ft^3/s)"\n'
            b'# //RATING_DATETIME BEGIN=20240122120000 END=20250122120000\n'
            b'INDEP\tDEP\n1.1\t10\n1.3\t20\n1.4\t20\n')
    def test_rating_never_extrapolates_or_matches_a_prefix(self):
        qs={'Q':15,'rounded':20,'outside':25}
        row=rating(self.sample,'12345678',qs)
        self.assertEqual(row['stage_brackets_ft'],{'Q':[1.1,1.4],'rounded':[1.3,1.4]})
        self.assertFalse(row['profile_in_range']['outside'])
        for raw,identifier in [(self.sample,'1234'),(self.sample.replace(b'USGS ',b'OTHER'),'12345678')]:
            with self.assertRaises(ValueError):rating(raw,identifier,qs)
        self.assertFalse(rating(self.sample+b'.8\t30\n','12345678',qs)['stage_brackets_ft'])

    def test_rating_stays_with_station_datum_and_period(self):
        common=dict(station='12345678',source={'path':'test'})
        qs={'Q':15}
        records=[dict(common,kind='gage',vertical_datum='NGVD29',distance_to_boundary_m=412),
                 dict(common,kind='rating',**rating(self.sample,'12345678',qs)),
                 dict(common,kind='gage_history',statement='Datum of gage is 10.00 ft above NAVD of 1988.'),
                 *[dict(common,kind='peak',date=d) for d in ('1982-01-01','2024-02-03','2026-02-03')]]
        row=boundary_evidence(records,qs,'NAVD88')[0]
        self.assertEqual(row['station_wse_bracket_ft'],[11.1,11.4])
        self.assertEqual(row['historical_dates_outside'],['1982-01-01','2026-02-03'])
        self.assertEqual(row['status'],'STATION_CONTEXT')
        self.assertIn('CONFLICTING_DATUM_METADATA',row['issues'])
        self.assertIn('BOUNDARY_TRANSFER_REQUIRED',row['issues'])
        records[2]['statement']+=' Earlier gage used a different zero.'
        self.assertIsNone(boundary_evidence(records,qs,'NAVD88')[0]['station_wse_bracket_ft'])

    def test_only_matched_event_with_usable_accuracy_has_an_interval(self):
        row=dict(role='boundary',kind='boundary_stage',event='spring',date='2024-02-03',event_eligible=True,issues=[],
                 location={'rs':'100'},model_datum='NAVD88',source='field notes',flow_cfs=450.,observed_ft=17.,uncertainty_ft=.2)
        self.assertEqual(event_tailwaters([row])[0]['interval_ft'],[16.8,17.2])
        for invalid in [dict(issues=['NO_MATCHED_EVENT_RUN']),dict(location={}),dict(source=''),dict(uncertainty_ft=0),
                        dict(uncertainty_ft=-1),dict(kind='bed'),dict(event=''),dict(model_datum='')]:
            self.assertIsNone(event_tailwaters([{**row,**invalid}])[0]['interval_ft'])
        holdout=dict(role='holdout',kind='stage',residual_ft=0.,uncertainty_ft=0.)
        self.assertEqual(holdout_stages([holdout]),([holdout],[holdout],[]))


class ActionTests(TestCase):
    def test_integrity_then_sensitive_control_then_alternative(self):
        def row(code,level,**facts):
            return finding(code,level,'qa',code,code,**facts)
        integrity=row('NATIVE_IDENTITY',0)
        candidate=row('GEOMETRY_FLOW_PATH',None,station='4200',baseline_share_pct=30.,alternative_share_pct=60.)
        boundary=row('BOUNDARY_INFLUENCE',2,area={'affected':0},delta_ft=2.,
                     area_case=dict(area=dict(affected=1,delta_ft=-.3,station='4300',compared=3)))
        area={'selected':['4200','4300']}
        actions=next_actions([row('BED_BASIS',2),boundary,integrity],[candidate],area,True)
        self.assertEqual([a['code'] for a in actions],['NATIVE_IDENTITY','BOUNDARY_INFLUENCE','GEOMETRY_FLOW_PATH','BED_BASIS'])
        self.assertEqual(actions[1]['facts']['station'],'4300')
        self.assertEqual(actions[1]['target'],'field-search')
        self.assertEqual(actions[2]['scope'],'CANDIDATE')
        self.assertEqual(next_actions([],[candidate],area,True),[])
