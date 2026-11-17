"""Input and provenance regressions; these are not site hydraulic results."""
import copy
import unittest
from unittest.mock import patch

from ras_workflow import intake, inputs, study
from ras_workflow.river import boundary_errors, boundary_cards
from ras_workflow.native_warnings import parse


def river():
    g=intake.blank_geometry('river')
    g.update(horizontal_crs='EPSG:26913',vertical_datum='SYNTHETIC_LOCAL',
             river='Test',reach='Reach',flow_regime='subcritical',
             channel_geometry_basis='conditional_surface_dem',
             boundaries={'downstream':{'type':'normal_depth'}},
             boundary_slopes={'downstream':.002},provenance=['synthetic unit test'])
    for i in range(4):
        g['cross_sections'].append(dict(rs=400-i*100,
            station_ft=[0,10,20,40,50,60],elevation_ft=[110,110,100,100,110,110],
            bank_stations_ft=[10,50],center_xy=[322000,4126300-i*30.48],
            cutline_xy=[[322009.144,4126300-i*30.48],[321990.856,4126300-i*30.48]],
            reach_lengths_ft=[100,100,100] if i<3 else [0,0,0],expansion_contraction=[.3,.1]))
    return g


class RiverContracts(unittest.TestCase):
    def test_absent_structure_is_valid_only_for_explicit_river(self):
        g=river();self.assertEqual(inputs.geometry_errors(g,True),[])
        g.pop('model_type');self.assertTrue(inputs.geometry_errors(g,True))

    def test_structure_cannot_be_hidden_by_river_mode(self):
        g=river();g['structure']['groups']=[{'count':3}]
        self.assertTrue(any('structure data' in e for e in inputs.geometry_errors(g,True)))

    def test_submerged_bed_basis_is_required(self):
        g=river();g.pop('channel_geometry_basis')
        self.assertTrue(any('bed representation' in e for e in inputs.geometry_errors(g,True)))

    def test_stage_profile_count_and_finite_values(self):
        g=river();g['boundaries']['downstream']={'type':'known_stage','stages_ft':[104,106]}
        self.assertEqual(boundary_errors(g,2),[])
        self.assertTrue(boundary_errors(g,1))
        self.assertIn('Dn Known WS=106.000000',boundary_cards(g,1))
        g['boundaries']['downstream']['stages_ft']=[float('nan')]
        self.assertTrue(boundary_errors(g,1))

    def test_saved_selector_can_introduce_stage_field(self):
        g=river();c={'scenarios':[{'id':'s','profiles':[{'id':'Q'}]}]}
        p={'original_project':{'path':'unused.json'},'scenario':'s'}
        d={'geometry':g,'answers':{'g.boundaries.downstream.type':{'value':'known_stage'},
                                  'g.boundaries.downstream.stages_ft':{'value':[104]}}}
        with patch.object(intake,'read',return_value=c):
            _,final=intake._objects(p,d)
        self.assertEqual(boundary_errors(final,1),[])
        self.assertEqual(final['boundaries']['downstream']['stages_ft'],[104])
        d['answers']['g.arbitrary_field']={'value':1}
        with patch.object(intake,'read',return_value=c),self.assertRaises(ValueError):intake._objects(p,d)

    def test_sensitivity_uses_only_active_boundary_without_culvert_n(self):
        g=river();s={'channel_n':.035,'overbank_n':.035,'profiles':[{'id':'Q'}]}
        changed,_,_=study.apply_changes(g,s,[{'path':'boundary_slopes.downstream','value':.003,'basis':'test'}],'software_validation')
        self.assertEqual(changed['boundary_slopes']['downstream'],.003)
        self.assertEqual(g['boundary_slopes']['downstream'],.002)
        g['boundaries']['downstream']={'type':'known_stage','stages_ft':[104]}
        changed,_,_=study.apply_changes(g,s,[{'path':'boundaries.downstream.stages_ft.0','value':105,'basis':'test'}],'software_validation')
        self.assertEqual(changed['boundaries']['downstream']['stages_ft'],[105])
        with self.assertRaises(ValueError):study.apply_changes(g,s,[{'path':'boundary_slopes.downstream','value':.003,'basis':'test'}],'software_validation')

    def test_native_zero_messages_requires_exact_complete_body(self):
        text='Errors Warnings and Notes for Plan : Workflow\n\n No Errors, Warnings or Notes in Computations\n'
        self.assertEqual(parse(text)['records'],[])
        with self.assertRaises(ValueError):parse(text+'Unexpected additional output\n')


if __name__=='__main__':unittest.main()
