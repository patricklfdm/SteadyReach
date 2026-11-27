"""Independent-variable controls and native comparison decisions."""
from copy import deepcopy
import unittest

from ras_workflow import factor_geometry as changes
from ras_workflow.factor_study import compare


class FactorChecks(unittest.TestCase):
    def setUp(self):
        self.g=dict(horizontal_crs='EPSG:26915',vertical_datum='NAVD88',hydraulic_unit='international_ft',
                    boundaries={'downstream':{'type':'known_stage','stages_ft':[9,11]}},cross_sections=[])
        for rs,y in [(200,50),(100,0)]:
            self.g['cross_sections'].append(dict(rs=rs,cutline_xy=[[0,y],[10,y]],station_ft=[0,2,5,8,10],
                elevation_ft=[5,4,0,4,5],bank_stations_ft=[2,8],expansion_contraction=[.3,.1],
                reach_lengths_ft=[100,100,100] if rs==200 else [0,0,0]))

    def test_boundary_changes_only_selected_profile_and_bed_only_between_banks(self):
        z=changes.outlet(self.g,12,1)
        self.assertEqual(z['boundaries']['downstream']['stages_ft'],[9,12])
        self.assertEqual(self.g['boundaries']['downstream']['stages_ft'],[9,11])
        b=changes.bed(self.g,-2)
        self.assertEqual(b['cross_sections'][0]['elevation_ft'],[5,4,-2,4,5])
        self.assertEqual(self.g['cross_sections'][0]['elevation_ft'],[5,4,0,4,5])

    def test_nested_does_not_accept_second_changed_factor(self):
        g=deepcopy(self.g)
        mid=deepcopy(g['cross_sections'][0])
        mid.update(rs=150,cutline_xy=[[0,25],[10,25]],reach_lengths_ft=[50]*3)
        g['cross_sections'][0]['reach_lengths_ft']=[50]*3
        g['cross_sections'].insert(1,mid)
        self.assertEqual(changes.nested(self.g,g)['cross_sections'],g['cross_sections'])
        g['cross_sections'][1]['expansion_contraction']=[.8,.4]
        with self.assertRaisesRegex(ValueError,'losses'):changes.nested(self.g,g)
        mid['expansion_contraction']=[.3,.1]
        g['cross_sections'][0]['bank_stations_ft']=[2,6]
        with self.assertRaisesRegex(ValueError,'original section'):changes.nested(self.g,g)

    def test_fewer_warnings_with_more_error_retains_parent(self):
        parent={'150':dict(wse_ft=7.,wet_left=True,wet_right=False)}
        alt={'150':dict(wse_ft=6.75,wet_left=False,wet_right=False)}
        r=compare(parent,alt,[dict(rs='150',observation_ft=9.,source='field')],[112,67])
        self.assertEqual(r['stop'],'RETAIN_PARENT_OBSERVATION_WORSENED')
        self.assertEqual(r['wet_sections'],[['150'],[]])
        self.assertEqual(r['checks'][0]['trial_error_ft'],-2.25)
        self.assertEqual(compare(parent,alt,[],[None,None])['stop'],'FIELD_CHECK_REQUIRED')
