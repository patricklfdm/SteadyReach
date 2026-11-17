import copy
import unittest
from unittest.mock import patch

from ras_workflow import result_atlas as atlas


def section(rs='200', profile='Q100', ident='0:0'):
    return dict(section_id=ident,rs=rs,profile=profile,river='R',reach='A',
        station_ft=[0.,2.,4.,6.,8.],elevation_ft=[3.,0.,3.,0.,3.],banks_ft=[2.,6.],
        wse_ft=1.,egl_ft=1.2,critical_wse_ft=None,velocity_fts=2.,froude=.5,
        channel_length_ft=30.,min_error_ft=0.)


class AtlasTests(unittest.TestCase):
    def test_two_geometric_wet_parts_are_interpolated_not_bank_width(self):
        row=section();parts=atlas.wet_parts(row['station_ft'],row['elevation_ft'],1.)
        self.assertEqual(len(parts),2)
        for value,expected in zip(parts[0],[4/3,8/3]):self.assertAlmostEqual(value,expected)
        for value,expected in zip(parts[1],[16/3,20/3]):self.assertAlmostEqual(value,expected)

    def test_exact_crest_does_not_claim_positive_depth_connection(self):
        self.assertEqual(atlas.wet_parts([0.,1.,2.],[0.,1.,0.],1.),[[0.,1.],[1.,2.]])

    def test_vertical_walls_remain_supported(self):
        self.assertEqual(atlas.wet_parts([0.,0.,2.,2.],[2.,0.,0.,2.],1.),[[0.,2.]])

    def test_dry_and_missing_water_are_distinct(self):
        self.assertEqual(atlas.wet_parts([0.,1.],[2.,3.],1.),[])
        self.assertIsNone(atlas.wet_parts([0.,1.],[2.,3.],None))

    def test_invalid_profile_does_not_get_partial_fabricated_picture(self):
        for x,z in [([1.,0.],[0.,1.]),([0.,1.],[0.,float('nan')]),([0.,1.],[0.]),([0.,0.],[0.,1.])]:
            with self.assertRaises(ValueError):atlas.wet_parts(x,z,1.)

    def test_matching_numeric_station_alias_and_global_message_retained(self):
        rows=[section()];before=copy.deepcopy(rows)
        issue=dict(id='one',profile='Q100',station='200.00',code='NATIVE_DIVIDED_FLOW',evidence={'river':'R','reach':'A'})
        global_issue=dict(id='two',profile=None,station=None,code='GAP',evidence={})
        other_reach=dict(issue,id='three',evidence={'river':'R','reach':'B'})
        result=atlas.assemble(rows,{'issues':[issue,global_issue,other_reach]})
        self.assertEqual(result['located_diagnostic_count'],1)
        self.assertEqual([v['id'] for v in result['unlocated_issues']],['two','three'])
        self.assertEqual(result['sections'][0]['issues'],[issue]);self.assertEqual(rows,before)

    def test_neighbors_cannot_cross_profile_or_reach_boundary(self):
        rows=[section('200','Q100','0:0'),section('100','Q100','0:1'),section('200','Q200','1:0'),section('100','Q200','1:1')]
        result=atlas.assemble(rows,{'issues':[]})['sections']
        self.assertEqual([n['section_id'] for n in result[1]['neighbors']],['0:0'])
        self.assertEqual([n['section_id'] for n in result[2]['neighbors']],['1:1'])
        self.assertEqual(result[1]['neighbors'][0]['channel_length_between_ft'],30.)

    def test_map_comes_from_bound_section_with_matching_station_domain(self):
        row=section();geom={'cross_sections':[dict(rs=200,station_ft=[0.,8.],cutline_xy=[[100.,50.],[108.,50.]])]}
        got=atlas.assemble([row],{'issues':[]},geom)['sections'][0]
        self.assertEqual(got['map']['banks_xy'],[[102.,50.],[106.,50.]])
        self.assertAlmostEqual(got['map']['wet_segments_xy'][0][0][0],100+4/3)
        geom['cross_sections'][0]['station_ft']=[0.,10.]
        self.assertIsNone(atlas.assemble([row],{'issues':[]},geom)['sections'][0]['map'])

    def test_edge_excess_does_not_substitute_bank_freeboard(self):
        row=section();row['elevation_ft'][0]=.5
        got=atlas.assemble([row],{'issues':[]})['sections'][0]
        self.assertEqual(got['left_excess_ft'],.5);self.assertEqual(got['right_excess_ft'],0)

    def test_bent_cutline_intersection_retains_vertices(self):
        self.assertEqual(atlas.line_slice([[0.,0.],[2.,0.],[2.,2.]],.25,.75),[[1.,0.],[2.,0.],[2.,1.]])

    def test_missing_water_stays_null_and_requires_attention(self):
        row=section();row['wse_ft']=None
        got=atlas.assemble([row],None)['sections'][0]
        self.assertIsNone(got['wet_intervals_ft']);self.assertIsNone(got['left_excess_ft'])
        self.assertTrue(got['needs_attention'])

    def test_each_profile_gets_its_own_level_and_warning(self):
        a=section();b=section(profile='Q200',ident='1:0');b['wse_ft']=4
        issue=dict(id='b',profile='Q200',station='200',code='WET_SECTION_EDGE',evidence={})
        result=atlas.assemble([a,b],{'issues':[issue]})['sections']
        self.assertEqual(len(result[0]['wet_intervals_ft']),2);self.assertEqual(result[0]['issues'],[])
        self.assertEqual(result[1]['wet_intervals_ft'],[[0.,8.]])
        self.assertEqual(result[1]['left_excess_ft'],1.)

    def test_changed_displayed_result_rejected_before_native_read(self):
        with patch('ras_workflow.result_guidance.load_evidence',side_effect=ValueError('changed evidence')),patch.object(atlas,'native_rows') as native:
            with self.assertRaisesRegex(ValueError,'changed evidence'):atlas.collect('x',{})
            native.assert_not_called()


if __name__=='__main__':unittest.main()
