"""Synthetic terrain tests for physical coverage and separated exterior endpoints."""
import unittest
import numpy as np
from ras_workflow import terrain_auto,banks
from ras_workflow.bank_reach import SETTINGS


class SyntheticSampler:
    factor=1.
    cell_ft=1.
    def sample(self,points):
        points=np.asarray(points,float)
        return np.clip((abs(points[:,0])-49)*.6,0,6)
    def stamp(self,row):row['synthetic_test_only']=True


class InitialSectionLayoutTests(unittest.TestCase):
    def test_narrow_relief_screen_does_not_crop_the_bank_break(self):
        sampler=SyntheticSampler()
        narrow=terrain_auto.width_row(sampler,[0,0],[0,-1])
        self.assertEqual(narrow['auto_layout']['width_ft'],120)
        self.assertIsNone(banks.propose(narrow,SETTINGS)['selected_indices'])
        widened=terrain_auto.width_row(sampler,[0,0],[0,-1],require_bank_coverage=True)
        self.assertGreater(widened['auto_layout']['width_ft'],120)
        self.assertIsNotNone(banks.propose(widened,SETTINGS)['selected_indices'])
        self.assertEqual(widened['auto_layout']['bank_coverage_extension_from_ft'],120)
        self.assertFalse(widened['auto_layout']['screen_is_water_level'])

    def test_missing_relief_retains_a_bounded_unresolved_profile(self):
        sampler=SyntheticSampler();sampler.sample=lambda p:np.zeros(len(p))
        row=terrain_auto.width_row(sampler,[0,0],[0,-1],maximum=240,require_bank_coverage=True)
        self.assertIsNone(row['bank_stations_ft'])
        self.assertEqual(row['auto_layout']['bank_coverage']['status'],'UNRESOLVED')
        self.assertLessEqual(row['auto_layout']['width_ft'],240)

    def test_missing_adjacent_dem_preserves_valid_original_samples(self):
        sampler=SyntheticSampler();original=sampler.sample
        def sample(points):
            result=original(points);result[np.abs(np.asarray(points)[:,0])>65]=np.nan;return result
        sampler.sample=sample
        row=terrain_auto.width_row(sampler,[0,0],[0,-1],require_bank_coverage=True)
        self.assertEqual(row['auto_layout']['width_ft'],120)
        self.assertTrue(np.isfinite(row['elevation_ft']).all())
        self.assertEqual(row['auto_layout']['bank_coverage']['status'],'UNRESOLVED')

    def test_near_duplicate_terminal_section_removed_endpoint_retained(self):
        sampler=SyntheticSampler()
        for length in (640.,641.24,659.,700.):
            rows,spacing=terrain_auto.adaptive_sections(sampler,[[0,length],[0,0]],'river',240)
            distances=np.diff([r['local_chainage_ft'] for r in rows])
            self.assertTrue((distances>=spacing*.35-1e-8).all())
            np.testing.assert_allclose(rows[0]['center_xy'],[0,length])
            np.testing.assert_allclose(rows[-1]['center_xy'],[0,0])
            self.assertEqual(rows[-1]['local_chainage_ft'],length)


if __name__=='__main__':unittest.main()
