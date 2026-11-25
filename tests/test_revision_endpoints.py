from unittest import TestCase
from unittest.mock import patch

from ras_workflow import revision_endpoints as ends
from ras_workflow.revision_review import metric_rows


class RevisionEndpointTests(TestCase):
    def setUp(self):
        self.loc={'100':dict(location_status='SAME_CENTER',rotation_degrees=0)}

    def compare(self,old,new):
        def values(rows):
            return {('Q100','100',side):('River','Reach',depth) for side,depth in rows}
        return ends.compare_ends(values(old),values(new),self.loc)

    def test_same_total_wet_count_can_hide_a_side_swap(self):
        result=self.compare([('left',-.2),('right',.5)],[('left',.3),('right',0)])
        self.assertEqual(result['counts'],dict(new_wet=1,still_wet=0,became_dry=1,both_dry=0,unmatched=0))
        self.assertEqual(result['rows'][0]['current_depth_ft'],.3)

    def test_larger_extent_can_stay_wet_and_depth_can_decrease(self):
        result=self.compare([('left',1),('right',0)],[('left',.5),('right',-.5)])
        self.assertEqual(result['counts']['still_wet'],1)
        self.assertEqual(result['counts']['both_dry'],1)
        self.assertEqual(len(result['rows']),1)

    def test_missing_edition_ground_or_direction_stays_unmatched(self):
        self.assertEqual(self.compare([], [('right',-1)])['rows'][0]['reason'],'absent')
        self.assertEqual(self.compare([('right',None)],[('right',.2)])['rows'][0]['reason'],'missing')
        for status,angle in [('MOVED',0),('UNVERIFIED',0),('SAME_CENTER',None),('SAME_CENTER',100)]:
            self.loc['100']=dict(location_status=status,rotation_degrees=angle)
            with self.subTest(status=status,angle=angle):
                self.assertEqual(self.compare([('left',1)],[('left',-1)])['counts']['unmatched'],1)

    def test_different_profile_or_reach_never_closes_old_wet_side(self):
        before={('Q100','100','left'):('River','A',1)}
        for after in [{('Q500','100','left'):('River','A',-1)},
                      {('Q100','100','left'):('River','B',-1)}]:
            counts=ends.compare_ends(before,after,self.loc)['counts']
            self.assertGreater(counts['unmatched'],0)
            self.assertEqual(counts['became_dry'],0)

    def test_unreadable_native_data_is_an_explicit_unknown(self):
        with patch.object(ends,'endpoints',side_effect=ValueError('inventory')):
            result=ends.summary({'unit':'international ft'},{'unit':'international ft'},{},{},{})
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertIsNone(result['counts'])

    def test_unknown_roadway_flow_and_real_zero_survive_display_selection(self):
        metric=dict(profile='Q100',metric='roadway_flow_software_cfs',previous=None,current=0.,change=None)
        rows=metric_rows([metric])
        self.assertIsNone(rows[0]['previous'])
        self.assertEqual(rows[0]['current'],0.)
        self.assertIsNone(rows[0]['change'])
