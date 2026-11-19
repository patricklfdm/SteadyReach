import copy
import unittest
from ras_workflow.river_comparison import comparison


class RiverAlternativesTests(unittest.TestCase):
    def section(self,wet):
        return dict(stage_ft=20.,flow_cfs=500.,ends_ft=[19. if w else 21. for w in wet],
                    wet=wet,ob_percent=[None,10.],critical_fallback=None,cut=[[0,1],[1,1]],center=[.5,1.])

    def test_equal_totals_can_hide_moved_wet_side(self):
        base={'200':self.section([False,False]),'100':self.section([True,False])}
        frames=dict(baseline=base,fixed=copy.deepcopy(base),rotated={'200':self.section([False,True]),'100':self.section([False,False])})
        rows,totals=comparison(frames)
        self.assertEqual(totals['fixed']['wet_sections'],totals['rotated']['wet_sections'])
        self.assertEqual(totals['rotated']['new_wet_ends'],1)
        self.assertEqual(totals['rotated']['cleared_wet_ends'],1)
        self.assertEqual(totals['rotated']['missing_fallbacks'],2)
        self.assertEqual(rows[0]['variants']['rotated']['new_wet'],[False,True])
        self.assertIsNone(rows[0]['variants']['rotated']['ob_percent'][0])

    def test_changed_flow_or_center_cannot_be_paired(self):
        for change in ({'center':[2,1]},{'flow_cfs':550.}):
            base={'100':self.section([False,True])};altered=copy.deepcopy(base);altered['100'].update(change)
            with self.assertRaises(ValueError):comparison(dict(baseline=base,fixed=copy.deepcopy(base),rotated=altered))
