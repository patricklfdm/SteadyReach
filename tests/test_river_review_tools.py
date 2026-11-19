import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ras_workflow.floodplain_path import corridor
from ras_workflow.operator_log import classify, inventory, record
from ras_workflow.river_review import key_inputs, local_problems, overbank_changes, response
from ras_workflow.section_direction import assess, crossing_issues, rotation_controls
from ras_workflow.section_joint import repair
from test_section_joint import fixture


class DirectionTests(unittest.TestCase):
    def test_two_scales_preserve_a_natural_bend(self):
        line = [[-20,0],[0,0],[20,0],[20,20],[20,40]]
        cuts = [[[0,-5],[0,5]], [[16,4],[24,-4]], [[15,20],[25,20]]]
        g = dict(model_type='river',flowlines=[dict(id='r',xy=line)],cross_sections=[
            dict(rs=i,reach_id='r',cutline_xy=cut) for i,cut in enumerate(cuts)])
        self.assertEqual([r['status'] for r in assess(g)],['TURN_FOLLOWS_CHANNEL']*3)
        g['cross_sections'][0]['cutline_xy'] = [[-3,-3],[3,3]]
        self.assertEqual(assess(g)[0]['status'],'SKEW_SUPPORTED_AT_TWO_SCALES')
        g['cross_sections'][0]['cutline_xy'] = [[-3,-5],[28,8]]
        self.assertEqual(crossing_issues(g)[0]['sections'],[0])

    def test_skip_rotations_that_submerge_formerly_dry_ends(self):
        g,s=fixture()
        g['model_type']='river'
        rows=g['cross_sections']
        for i,row in enumerate(rows):
            y=40.*i
            row.update(cutline_xy=[[-8.,y-6.],[8.,y+6.]],center_xy=[0.,y],
                       station_ft=np.linspace(0,20,21).tolist())
        ends=np.array([p for row in rows for p in row['cutline_xy']])
        def ridges(points):
            distance=np.linalg.norm(np.asarray(points)[:,None,:]-ends[None,:,:],axis=2)
            return np.where(distance.min(axis=1)<.03,10.,0.)
        s.sample=ridges
        for row in rows:
            a,b=np.asarray(row['cutline_xy'])
            row['elevation_ft']=ridges(a+np.linspace(0,1,21)[:,None]*(b-a)).tolist()
            s.stamp(row)
        self.assertTrue(repair(g,s,{},20.)['changes'])
        result=repair(g,s,{},20.,prior_stages={r['rs']:5. for r in rows})
        self.assertFalse(result['changes'])
        self.assertTrue(any(a['rejected'].get('ROTATION_TRUNCATES_PREVIOUSLY_DRY_SECTION')
                            for a in result['search']['attempts']))

    def test_fixed_direction_receipt_remains_replayable(self):
        g,s=fixture()
        g['model_type']='river'
        fixed=repair(g,s,{200.:10.},100.,allow_rotation=False)
        self.assertNotIn('directions',fixed['search'])
        self.assertTrue(all(r['rotation_deg']==0 for r in fixed['changes']))

    def test_external_controls_lock_rotation_but_allow_straight_extension(self):
        g,s = fixture()
        rows = g['cross_sections']
        answers = {'g.cross_sections.0.bank_stations_ft':dict(value=[5,15]),
                   'g.cross_sections.1.bank_stations_ft':dict(value=[5,15],automatic_preparation=True)}
        self.assertEqual(rotation_controls(rows,answers),{0})
        out=repair(g,s,{200.:10.,100.:10.},100.,rotation_locks={0})
        self.assertFalse(any(r['rotation_deg'] for r in out['changes'] if r['rs']==200.))
        rows[1]['terrain_review']=dict(identity='LOCAL_SELECTION_NO_ENGINEERING_REVIEW')
        self.assertEqual(rotation_controls(rows,answers),{0,1})


class FloodplainTests(unittest.TestCase):
    def test_only_a_connected_path_can_support_an_extension(self):
        def cut(y):
            return dict(cutline_xy=[[0,y],[10,y]],station_ft=[0,10],bank_stations_ft=[4,7])
        class Raster:
            cell_ft=factor=1.
            def sample(self,points):
                return np.where(np.abs(points[:,1]-5.)<=.5,self.barrier,0.)
        raster=Raster()
        def result(barrier,stages=(1.,3.)):
            raster.barrier=barrier
            return corridor(cut(0),cut(10),0,raster,stages,4.)['status']
        self.assertEqual(result(0.),'LOW_ROUTE_AT_BOTH_STAGES')
        self.assertEqual(result(1.5),'STAGE_DEPENDENT_LOW_ROUTE')
        self.assertEqual(result(4.),'NO_CONNECTED_LOW_ROUTE_IN_STRIP')
        self.assertEqual(result(np.nan),'INCOMPLETE_DEM')


class ReviewTests(unittest.TestCase):
    def test_sensitivity_counts_and_sign_by_profile(self):
        cases=[dict(id='low',changes=[dict(path='boundary_slopes.upstream')])]
        comp=dict(case='low',cross_section_differences=[dict(profile=p,station=i,delta_wse_ft=v)
            for p,i,v in [('Q100',100,-.21),('Q100',200,.10),('other',100,.17)]])
        rows=response([dict(cases=cases,comparisons=[comp],analysis={'path':'record'})])
        self.assertEqual([r['signed_peak_ft'] for r in rows],[-.21,.17])
        self.assertEqual(rows[0]['affected'],[dict(rs=100,delta_ft=-.21)])
        self.assertEqual(rows[0]['compared'],2)

    def test_nonuniform_stations_and_profiles_stay_separate(self):
        records=[dict(station=rs,profile=p,code='WET',id=str(i)) for i,(p,rs) in
                 enumerate([('a',525),('a',482.5),('a',100),('b',482.5)])]
        action=dict(id='edges',title='Coverage',target='coverage',explanation='check',issue_ids=['1'],issue_records=records)
        groups=local_problems([action],[525,482.5,300,100])
        self.assertEqual([r['stations'] for r in groups],[['525','482.5'],['100'],['482.5']])
        self.assertEqual(sum(r['records'] for r in groups),len(records))

    def test_manual_bank_pair_survives_terrain_reassessment(self):
        from ras_workflow.bank_reassessment import matches_terrain_candidate
        from ras_workflow.bank_autoprepare import protected
        g,_=fixture()
        g['model_type']='river'
        row=g['cross_sections'][0]
        row['bank_candidates']=dict(method='reach_bank_dynamic_programming_v3',evidence_class='inferred',
            selected_indices=[3,16],confidence='LOW',reasons=['COMPETING_LEFT_BANKS'])
        row['bank_stations_ft']=[row['station_ft'][i] for i in (3,16)]
        self.assertTrue(matches_terrain_candidate(row))
        self.assertNotIn(('river',200.),protected(g,{}))
        row['bank_stations_ft'][0]+=1.
        self.assertFalse(matches_terrain_candidate(row))
        self.assertIn(('river',200.),protected(g,{}))

    def test_source_choice_remains_adopted(self):
        r=key_inputs([dict(key='c.scenarios.0.flow_cfs',value=100,unit='cfs',evidence_class='assumed',
            parameter_candidates=[{'value':94},{'value':94}],answer={'basis':'nearby gage'})])[0]
        self.assertEqual((r['value'],r['alternatives'],r['priority']),(100,[94],'OTHER_CANDIDATES'))
        self.assertEqual(key_inputs([dict(key='s.flow_cfs',value=100)])[0]['priority'],'BASIS_MISSING')

    def test_native_floodplain_shares_only_compared_at_common_centers(self):
        values=[{10.:(12.,.5,.2),5.:(8.,.4,.2)},{10.:(13.,.6,0.),5.:(9.,.6,.1)}]
        with patch('ras_workflow.lateral_coverage.hydraulic_context',side_effect=values):
            rows=overbank_changes({},{},{'10':dict(location_status='SAME_CENTER'),'5':dict(location_status='MOVED')})['rows']
        self.assertEqual(len(rows),1)
        np.testing.assert_allclose(rows[0]['delta_points'],[10,-20])

    def test_operator_receipts_count_confirmations_and_ignore_reads(self):
        self.assertIsNone(classify('qa-guidance',{}))
        self.assertIsNone(classify('save',{'values':{}}))
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.assertEqual(inventory(folder)['coverage'],'NO_RECORDED_HISTORY')
            record(folder,'revision',classify('revision',{}),'local_api')
            record(folder,'start',classify('start',{}),'workflow_page')
            self.assertEqual(inventory(folder)['counts'],{'decision_requests':2,'compute_consents':1})
            (folder/'operator_actions'/'broken.json').write_text('{',encoding='utf8')
            self.assertEqual(inventory(folder)['coverage'],'PARTIAL_HISTORY')
            self.assertEqual(inventory(folder)['recorded_requests'],2)
