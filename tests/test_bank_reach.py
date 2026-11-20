import copy
import unittest
from unittest.mock import patch

from ras_workflow import bank_reach


def geometry():
    rows = []
    for index in range(3):
        rows.append(dict(rs=300.-index*100,reach_id='river',center_xy=[50.,index*100.],
            cutline_xy=[[0.,index*100.],[100.,index*100.]],station_ft=list(range(101)),
            elevation_ft=[10.+max(0,abs(x-50)-20)*.2 for x in range(101)],bank_stations_ft=None))
    return dict(horizontal_crs='EPSG:26913',cross_sections=rows,flowlines=[{}],structure={})


def local(left=20,right=80):
    def choice(index):
        return dict(index=index,station_ft=float(index),score=1.,scale_support=3)
    return dict(reasons=['DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED'] if left is not None else ['NO_SCALE_STABLE_BANK_PAIR'],
        selected_indices=[left,right] if left is not None else None,channel_minimum_index=50,
        left=[choice(left)] if left is not None else [],right=[choice(right)],
        confidence='MEDIUM' if left is not None else 'UNRESOLVED')


class ReachBanks(unittest.TestCase):
    def test_joint_path_and_input_immutability(self):
        g=geometry();before=copy.deepcopy(g)
        with patch.object(bank_reach,'propose',side_effect=[local(),local(),local()]):
            result,summary=bank_reach.propose_reach(g,[])
        self.assertEqual(g,before)
        self.assertEqual(summary['proposed_pairs'],3)
        self.assertEqual([r['selected_indices'] for r in result],[[20,80]]*3)

    def test_competing_bank_evidence_can_be_saved_with_geometry(self):
        import json
        choice=local()
        choice['left'].append(dict(index=30,station_ft=30.,score=.9,scale_support=3))
        with patch.object(bank_reach,'propose',side_effect=[choice,choice,choice]):
            results,_=bank_reach.propose_reach(geometry(),[])
        side=results[1]['continuity']['side_evidence']['left']
        self.assertIsNotNone(side['conditional_cost_margin'])
        self.assertIs(type(side['distinct']),bool)
        json.dumps(results,allow_nan=False)

    def test_single_missing_interior_pair_has_explicit_assumption(self):
        g=geometry()
        with patch.object(bank_reach,'propose',side_effect=[local(),local(None),local()]):
            result,summary=bank_reach.propose_reach(g,[])
        self.assertEqual(summary['interpolated_indices'],[1])
        self.assertEqual(result[1]['evidence_class'],'assumed')
        self.assertEqual(result[1]['confidence'],'LOW')
        self.assertEqual(result[1]['continuity']['source'],'neighbor_bank_interpolation')
        self.assertEqual([r['rs'] for r in result[1]['continuity']['interpolation_neighbors']],[300.,100.])

    def test_no_interpolation_across_structure_or_reach(self):
        for kind in ['structure','reach']:
            g=geometry()
            if kind=='structure':g['structure']=dict(us_xs_rs=300.,ds_xs_rs=200.)
            else:g['cross_sections'][0]['reach_id']='other'
            with self.subTest(kind=kind), patch.object(bank_reach,'propose',side_effect=[local(),local(None),local()]):
                result,summary=bank_reach.propose_reach(g,[])
            self.assertIsNone(result[1]['selected_indices'])
            self.assertEqual(summary['interpolated_indices'],[])

    def test_saved_manual_controls_survive_refresh(self):
        g=geometry();g['cross_sections'][1]['bank_stations_ft']=[22.5,78.5]
        with patch.object(bank_reach,'propose',side_effect=[local(),local(),local()]):
            bank_reach.refresh(g)
        self.assertEqual(g['cross_sections'][1]['bank_stations_ft'],[22.5,78.5])
        self.assertEqual(g['bank_reach_summary']['locked_indices'],[1])
        with patch.object(bank_reach,'propose',side_effect=AssertionError('Unchanged inputs should reuse proposals')):
            bank_reach.refresh(g)

    def test_geometry_context_includes_crs_faces_and_remote_control(self):
        g=geometry();first=bank_reach.signature(g,{2})
        g['structure']['us_xs_rs']=300.
        self.assertNotEqual(first,bank_reach.signature(g,{2}))
        second=bank_reach.signature(g,{2});g['horizontal_crs']='EPSG:26914'
        self.assertNotEqual(second,bank_reach.signature(g,{2}))
        third=bank_reach.signature(g,{2});g['cross_sections'][2]['bank_stations_ft']=[25.,75.]
        self.assertNotEqual(third,bank_reach.signature(g,{2}))

    def test_nearer_supported_shoulder_outranks_remote_valley_wall(self):
        row=geometry()['cross_sections'][0]
        choice=local(20,95)
        choice['right'][0].update(relief_ft=90.,score=2.)
        choice['right'].append(dict(index=65,station_ft=65.,relief_ft=3.,score=1.,scale_support=3))
        pairs=bank_reach._options(row,choice,False)
        self.assertEqual(min(pairs,key=lambda p:p['cost'])['indices'],[20,65])
        self.assertEqual(pairs[0]['hillside_comparisons'][0]['inner_ft'],65.)
        choice['right'][1]['scale_support']=1
        self.assertFalse(bank_reach._options(row,choice,False)[0]['hillside_comparisons'])

    def test_missing_profile_is_unresolved(self):
        g=geometry();g['cross_sections'][1].pop('station_ft')
        result,summary=bank_reach.propose_reach(g,[])
        self.assertIsNone(result[1]['selected_indices'])
        self.assertIn(1,summary['unresolved_indices'])


if __name__=='__main__':
    unittest.main()
