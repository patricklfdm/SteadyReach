"""Revision review reports verified per-section changes and incomplete coverage."""
import copy
import unittest
from unittest.mock import patch

from ras_workflow import app_revision, qa


def summary():
    profile=dict(profile_id='Q100',flow_cfs=100.,headwater_rs='200',tailwater_rs='100',
        metrics=dict(upstream_wse_ft=20.,downstream_wse_ft=10.,max_channel_velocity_fts=3.,max_channel_froude=.5))
    return dict(hydraulics=dict(datum='NAVD88',unit='international ft',model_type='river',
        case_kind='site_conditional',profiles=[profile],raw_hdf={},raw_controller={}))


class RevisionComparison(unittest.TestCase):
    def compare(self,old=None,new=None,water=None):
        old=old or summary();new=new or copy.deepcopy(old)
        water=water or [{'Q100':{'200':20.,'100':10.}}, {'Q100':{'200':20.2,'100':10.}}]
        with patch.object(app_revision,'intact',return_value=True), \
             patch.object(app_revision,'read',return_value=old), \
             patch.object(qa,'verified_profiles',side_effect=water):
            return app_revision.compare(dict(parent_revision=dict(summary=dict(path='parent.json'))),new)

    def test_all_sections_and_river_metrics(self):
        result=self.compare()
        self.assertEqual(result['status'],'COMPARISON_NOT_ACCEPTANCE')
        self.assertEqual(len(result['cross_sections']),2)
        self.assertEqual(result['profiles'][0]['maximum']['station'],'200')
        self.assertTrue(result['profiles'][0]['exceeds_review_threshold'])
        self.assertEqual(result['rows'][2]['metric'],'max_channel_velocity_fts')
        self.assertEqual(result['diagnostics']['previous']['status'],'UNAVAILABLE')

    def test_changed_endpoint_omits_metric_delta_and_tracks_sections(self):
        new=summary();new['hydraulics']['profiles'][0]['headwater_rs']='300'
        result=self.compare(new=new,water=[{'Q100':{'200':20.,'100':10.}}, {'Q100':{'300':25.,'100':10.2}}])
        self.assertTrue(result['rows'][0]['location_changed'])
        self.assertIsNone(result['rows'][0]['change'])
        self.assertEqual(result['profiles'][0]['added_stations'],['300'])
        self.assertEqual(result['profiles'][0]['removed_stations'],['200'])

    def test_different_flow_and_datum_are_incompatible(self):
        for kind in ('flow','datum'):
            new=summary()
            if kind=='flow':new['hydraulics']['profiles'][0]['flow_cfs']=101.
            else:new['hydraulics']['datum']='other'
            with self.subTest(kind=kind):
                self.assertEqual(self.compare(new=new)['status'],'COMPARISON_INCOMPATIBLE')

    def test_raw_error_and_nonfinite_value_stay_visible(self):
        for water in ([ValueError('Raw result hashes no longer match')],
                      [{'Q100':{'200':20.}},{'Q100':{'200':float('nan')}}]):
            result=self.compare(water=water)
            self.assertEqual(result['status'],'COMPARISON_UNAVAILABLE')
            self.assertEqual(result['rows'],[])

    def test_no_matching_profiles_is_not_success(self):
        new=summary();new['hydraulics']['profiles'][0]['profile_id']='Q200'
        result=self.compare(new=new,water=[{'Q100':{'200':20.}},{'Q200':{'200':21.}}])
        self.assertEqual(result['status'],'COMPARISON_INCOMPATIBLE')

    def test_native_supplement_counts_replace_partial_diagnostics(self):
        current=summary();current['hydraulics']['diagnostics']=dict(path='qa.json')
        current['native_supplement']={}
        # A real manifest is truthy. The fixture isolates the diagnostic routing.
        current['native_supplement']['path']='native.json'
        full=dict(counts={'NATIVE_WARNING':4},issues=[{}]*4,warning_coverage='FULL')
        with patch.object(app_revision,'intact',return_value=True), \
             patch.object(app_revision,'read',return_value={}), \
             patch('ras_workflow.app_outputs.validate',return_value=dict(warnings=dict(records=[{}]*4))), \
             patch('ras_workflow.app_outputs.diagnostics',return_value=full):
            result=app_revision._diagnostic_summary(current)
        self.assertEqual(result['native_messages'],4)
        self.assertEqual(result['warning_coverage'],'FULL')
        self.assertEqual(result['counts'],{'NATIVE_WARNING':4})


if __name__=='__main__':unittest.main()
