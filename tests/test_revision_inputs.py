import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ras_workflow import revision_inputs as revision, app_revision
from ras_workflow.common import ROOT, item, save


def geometry():
    return dict(horizontal_crs='EPSG:26913',vertical_datum='NAVD88',cross_sections=[dict(rs=100,
        station_ft=[0,10,20],elevation_ft=[5,0,5],bank_stations_ft=[5,15],
        center_xy=[10,0],cutline_xy=[[0,0],[20,0]],reach_lengths_ft=[0,0,0],expansion_contraction=[.3,.1])])


class RevisionInputsTests(unittest.TestCase):
    def test_extension_does_not_claim_that_renumbered_bank_stations_moved(self):
        old=geometry();new=copy.deepcopy(old);row=new['cross_sections'][0]
        row.update(station_ft=[0,10,20,30],elevation_ft=[6,5,0,5],bank_stations_ft=[15,25],cutline_xy=[[-10,0],[20,0]])
        result=revision.geometry_changes(old,new)
        self.assertEqual(result['changed_sections'],1)
        self.assertEqual(result['moved_centers'],0)
        self.assertEqual(result['moved_bank_pairs'],0)
        self.assertEqual(result['sections'][0]['bank_plan_shifts_ft'],[0,0])

    def test_moved_center_and_rotation_are_quantified(self):
        old=geometry();new=copy.deepcopy(old);row=new['cross_sections'][0]
        row.update(center_xy=[11,2],cutline_xy=[[11,-8],[11,12]])
        result=revision.geometry_changes(old,new)
        self.assertEqual(result['moved_centers'],1)
        self.assertEqual(result['moved_bank_pairs'],1)
        self.assertAlmostEqual(result['sections'][0]['center_shift_ft'],(5**.5)/.3048)
        self.assertEqual(result['sections'][0]['rotation_degrees'],90)

    def test_different_crs_cannot_claim_coincident_positions(self):
        old=geometry();new=copy.deepcopy(old);new['horizontal_crs']='EPSG:26914'
        result=revision.geometry_changes(old,new)
        self.assertEqual(result['unverified_centers'],1)
        self.assertIsNone(result['sections'][0]['center_shift_ft'])

    def test_repeated_ids_cannot_be_silently_combined(self):
        old=geometry();old['cross_sections']*=2
        with self.assertRaisesRegex(ValueError,'Repeated'):
            revision.geometry_changes(old,geometry())

    def test_missing_banks_and_native_section_controls_are_not_omitted(self):
        old=geometry();new=copy.deepcopy(old)
        row=new['cross_sections'][0]
        row.pop('bank_stations_ft')
        row['ineffective_left']={'station_ft':3,'elevation_ft':5}
        row['manning_segments']=[{'station_ft':0,'n':.05}]
        result=revision.geometry_changes(old,new)
        self.assertEqual(result['unverified_bank_pairs'],1)
        self.assertIn('ineffective_left',result['sections'][0]['changed_fields'])
        self.assertIn('manning_segments',result['sections'][0]['changed_fields'])

    def test_native_input_manifest_binds_config_and_geometry(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            folder=Path(temp);(folder/'project').mkdir()
            config=dict(geometry='geometry.json',scenarios=[])
            save(folder/'inputs/initial.json',config);save(folder/'inputs/geometry.json',geometry())
            save(folder/'manifest.json',dict(run_id='real-identity-fixture',input_snapshots=[item(folder/'inputs/initial.json'),item(folder/'inputs/geometry.json')]))
            summary=dict(configuration=config,hydraulics=dict(run_id='real-identity-fixture',raw_hdf={'path':str(folder/'project/Model.p01.hdf')}))
            actual=revision.bound_inputs(summary)
            self.assertEqual(actual[1],geometry())
            save(folder/'inputs/geometry.json',dict(geometry(),vertical_datum='changed'))
            with self.assertRaisesRegex(ValueError,'snapshots'):
                revision.bound_inputs(summary)

    def test_different_control_and_geometry_changes_are_not_spacing_only(self):
        config=dict(scenarios=[dict(id='q100',profiles=[dict(id='Q100',flow_cfs=15030)],channel_n=.0425,overbank_n=.11)])
        old=geometry();new=copy.deepcopy(old)
        old['boundary_slopes']={'downstream':.011647};new['boundary_slopes']={'downstream':.003377}
        new['cross_sections'][0]['elevation_ft']=[6,0,5]
        summaries=[dict(hydraulics=dict(scenario_id='q100'))]*2
        with patch.object(revision,'bound_inputs',side_effect=[(config,old,[]),(config,new,[])]):
            result=revision.collect(*summaries)
        self.assertEqual(result['interpretation'],'MULTIPLE_INPUT_CHANGES')
        self.assertEqual(result['input_changes'][0]['field'],'boundary_slopes.downstream')

    def test_missing_evidence_stays_unavailable(self):
        with patch.object(revision,'bound_inputs',side_effect=ValueError('Changed hash')):
            result=revision.collect({}, {})
        self.assertEqual(result['status'],'UNAVAILABLE')

    def test_largest_id_difference_at_moved_center_is_not_coincident_maximum(self):
        hyd=dict(datum='NAVD88',unit='international ft',model_type='river',case_kind='site_conditional',
            raw_hdf={},raw_controller={},profiles=[dict(profile_id='Q100',flow_cfs=15030,
                headwater_rs='200',tailwater_rs='100',metrics={'downstream_wse_ft':10})])
        old=dict(hydraulics=hyd)
        context=dict(status='VERIFIED',sources=[],geometry={'sections':[
            dict(station='100',location_status='MOVED',center_shift_ft=20,changed_fields=['center_xy']),
            dict(station='200',location_status='SAME_CENTER',center_shift_ft=0,changed_fields=[])]})
        with patch.object(app_revision,'intact',return_value=True), \
             patch.object(app_revision,'read',return_value=old), \
             patch('ras_workflow.qa.verified_profiles',side_effect=[{'Q100':{'100':10,'200':20}},{'Q100':{'100':12,'200':20.1}}]), \
             patch.object(revision,'collect',return_value=context):
            result=app_revision.compare({'parent_revision':{'summary':{'path':'old.json'}}},copy.deepcopy(old))
        self.assertEqual(result['profiles'][0]['maximum']['station'],'100')
        self.assertEqual(result['profiles'][0]['maximum_at_verified_centers']['station'],'200')
        self.assertEqual(result['profiles'][0]['verified_center_count'],1)
        endpoint=next(r for r in result['rows'] if r['metric']=='downstream_wse_ft')
        self.assertTrue(endpoint['location_changed'])
        self.assertIsNone(endpoint['change'])


if __name__=='__main__':
    unittest.main()
