"""Synthetic geometry contracts, separate from actual site computation evidence."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from pyproj import CRS

from ras_workflow import section_spacing as spacing
from ras_workflow.convergence import nonspacing_signature, validate_nested
from ras_workflow.geometry_qa import review_errors


def fixture():
    rows=[]
    for i in range(4):
        y=300-i*100
        rows.append(dict(rs=float(400-i*100),center_xy=[0,y],cutline_xy=[[-50,y],[50,y]],
            station_ft=[0,25,50,75,100],elevation_ft=[10,5,0,5,10],bank_stations_ft=[25,75],
            reach_lengths_ft=[110,100,120] if i<3 else [0,0,0],expansion_contraction=[.3,.1]))
    geometry=dict(model_type='river',horizontal_crs='EPSG:26913',vertical_datum='TEST',
        cross_sections=rows,flowlines=[dict(id='river',xy=[[0,300],[0,0]])],terrain_review_required=True)
    sampler=SimpleNamespace(crs=CRS.from_epsg(26913),datum='TEST',factor=1.,cell_ft=1.,
        source=dict(path='synthetic',sha256='fixture'),sample=lambda points:np.abs(points[:,0])/5,
        stamp=lambda row:None)
    return geometry,sampler


class SectionSpacingTests(unittest.TestCase):
    def test_spacing_result_preserves_existing_parameter_study(self):
        from ras_workflow import app_study
        previous=dict(path='existing-parameter-analysis.json',sha256='previous')
        model=dict(active_study=dict(study=dict(path='test-study.json'),review=dict(path='test-review.json')),
                   latest_study=previous,pending_study=dict(path='test-study.json'))
        entry=dict(path='spacing-analysis.json',sha256='spacing')
        with patch.object(app_study.core,'model',return_value=model), \
             patch.object(app_study,'intact',return_value=True), \
             patch.object(app_study.study,'run',return_value=dict(analysis_kind='section_spacing',status='NOT_CONVERGED')), \
             patch.object(app_study,'item',return_value=entry), \
             patch.object(app_study.core,'persist'):
            app_study.execute('isolated-test')
        self.assertEqual(model['latest_study'],previous)
        self.assertEqual(model['latest_spacing'],entry)
        self.assertNotIn('pending_study',model)
        self.assertTrue(model['exports_need_refresh'])

    def test_two_nested_refinements_preserve_profiles_and_lengths(self):
        g,s=fixture();original=copy.deepcopy(g)
        targets=spacing.intervals(g,[],'all')
        first,added,next_targets=spacing.refine(g,targets,s)
        second,_,_=spacing.refine(first,next_targets,s)
        self.assertEqual([len(x['cross_sections']) for x in (g,first,second)],[4,7,13])
        validate_nested(g,dict(first,approved_for_model=g.get('approved_for_model'),status=g.get('status'),spacing_trial=g.get('spacing_trial')))
        self.assertEqual(g,original)
        for old in g['cross_sections']:
            new=next(r for r in second['cross_sections'] if r['rs']==old['rs'])
            for key in ('station_ft','elevation_ft','bank_stations_ft','cutline_xy'):
                self.assertEqual(old[key],new[key])
        self.assertEqual(sum(r['reach_lengths_ft'][2] for r in second['cross_sections']),360.)
        self.assertEqual(added[0]['sampled_points'],101)

    def test_warning_selection_does_not_include_unrelated_messages(self):
        g,_=fixture()
        chosen=spacing.intervals(g,[dict(station='200.00',code='NATIVE_ENERGY_NOT_BALANCED'),
            dict(station='400.00',code='NATIVE_UNCLASSIFIED_MESSAGE')],'warnings')
        self.assertEqual([(r['upstream_rs'],r['downstream_rs']) for r in chosen],[(300.,200.),(200.,100.)])
        with self.assertRaises(ValueError):spacing.intervals(g,[],'warnings')

    def test_new_banks_are_actual_samples_at_physical_cut_width(self):
        g,s=fixture();g['cross_sections'][1]['cutline_xy']=[[-100,200],[100,200]]
        g['cross_sections'][1]['station_ft']=[0,50,100,150,200]
        g['cross_sections'][1]['bank_stations_ft']=[50,150]
        out,changes,_=spacing.refine(g,[dict(upstream_rs=400.,downstream_rs=300.)],s)
        new=out['cross_sections'][1]
        self.assertEqual(new['station_ft'][-1],150.)
        self.assertEqual(new['bank_stations_ft'],[37.5,112.5])
        self.assertTrue(all(b in new['station_ft'] for b in new['bank_stations_ft']))

    def test_no_data_or_ambiguous_flowline_is_rejected(self):
        g,s=fixture();targets=spacing.intervals(g,[],'all')
        s.sample=lambda points:np.full(len(points),np.nan)
        with self.assertRaisesRegex(ValueError,'NoData'):spacing.refine(g,targets,s)
        g,s=fixture();g['flowlines'][0]['xy']=[[0,300],[0,0],[20,300]]
        with self.assertRaisesRegex(ValueError,'crossing'):spacing.refine(g,targets,s)

    def test_explicit_controls_are_never_copied_to_new_sections(self):
        for field in ('manning_segments','ineffective_left','ineffective_right'):
            g,s=fixture();g['cross_sections'][0][field]=[1,2]
            with self.assertRaisesRegex(ValueError,'section-specific'):spacing.refine(g,spacing.intervals(g,[],'all'),s)

    def test_baseline_water_screen_extends_only_added_rows(self):
        g,s=fixture();s.unit='m';s.stamp=lambda row:spacing.Sampler.stamp(s,row)
        original=copy.deepcopy(g)
        out,changes,_=spacing.refine(g,spacing.intervals(g,[],'all'),s,[(0.,12.),(300.,12.)])
        self.assertEqual(g,original)
        for row in out['cross_sections']:
            if row['rs'] in (400.,300.,200.,100.):
                before=next(r for r in g['cross_sections'] if r['rs']==row['rs'])
                self.assertEqual(row['elevation_ft'],before['elevation_ft'])
                self.assertEqual(row['cutline_xy'],before['cutline_xy'])
            else:
                self.assertGreater(min(row['elevation_ft'][0],row['elevation_ft'][-1]),12.)
                self.assertTrue(all(b in row['station_ft'] for b in row['bank_stations_ft']))

    def test_confirmation_is_needed_for_new_terrain_reviews(self):
        g,s=fixture();out,_,_=spacing.refine(g,spacing.intervals(g,[],'all'),s)
        self.assertFalse(out['approved_for_model']);self.assertTrue(review_errors(out))
        confirmed=spacing.confirm_geometry(out,dict(path='explicit-test-confirmation'))
        self.assertTrue(confirmed['approved_for_model']);self.assertEqual(review_errors(confirmed),[])

    def test_nested_contract_rejects_changed_controls_and_lengths(self):
        g,s=fixture();out,_,_=spacing.refine(g,spacing.intervals(g,[],'all'),s)
        previous=dict(model_type='river',channel_n=.04,cross_sections=g['cross_sections'])
        current=dict(previous,cross_sections=out['cross_sections'])
        validate_nested(previous,current)
        for change in ('roughness','bank','length'):
            modified=copy.deepcopy(current)
            if change=='roughness':modified['channel_n']=.05
            if change=='bank':modified['cross_sections'][0]['bank_stations_ft'][0]=20
            if change=='length':modified['cross_sections'][1]['reach_lengths_ft'][2]+=1
            with self.assertRaises(ValueError):validate_nested(previous,modified)

    def test_river_native_signature_accepts_zero_structures_only(self):
        geometry='Type RM Length L Ch R = 1 ,400,100,100,100\nsection\nType RM Length L Ch R = 1 ,100,0,0,0\n'
        self.assertEqual(nonspacing_signature(geometry,'Mixed Flow\n','river'),([], 'Mixed Flow\n'))
        with self.assertRaises(ValueError):nonspacing_signature(geometry+'Type RM Length L Ch R = 2 ,200,0,0,0\n','Mixed Flow\n','river')
        with self.assertRaises(ValueError):nonspacing_signature(geometry,'Mixed Flow\n')


if __name__=='__main__':unittest.main()
