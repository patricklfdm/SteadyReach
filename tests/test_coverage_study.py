"""Synthetic batch contracts. Actual Pagosa evidence is kept outside test fixtures."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ras_workflow import coverage_study as coverage
from ras_workflow.common import read, save, sha
from ras_workflow.section_joint import repair
from test_section_joint import fixture


class CoverageTests(unittest.TestCase):
    def extended(self):
        geometry, sampler = fixture()
        geometry['cross_sections'] = geometry['cross_sections'][:1]
        geometry['cross_sections'][0]['ineffective_left'] = [3., 5., False]
        result = repair(geometry, sampler, {200.: 10.}, 120., allow_rotation=False)
        self.assertTrue(result['changes'])
        return geometry, result['geometry'], sampler

    def test_fixed_direction_preserves_interior_and_plan_banks(self):
        before, after, sampler = self.extended()
        coverage.validate_extension(before, after, sampler, 120.)
        row = after['cross_sections'][0]
        self.assertGreater(min(row['elevation_ft'][0], row['elevation_ft'][-1]), 10.)
        original, sampler = fixture()
        result = repair(original, sampler, {200.: 10., 100.: 10.}, 120., allow_rotation=False)
        self.assertEqual(json.loads(json.dumps(result)), result)
        coverage.validate_extension(original, result['geometry'], sampler, 120.)
        self.assertTrue(result['unresolved'])
        self.assertTrue(all(c['rotation_deg'] == 0 for c in result['changes']))

    def test_rejects_interior_banks_boundaries_and_direction_changes(self):
        old, proposed, sampler = self.extended()
        for mode in ('interior', 'bank', 'boundary', 'direction', 'coefficient', 'roughness', 'ineffective'):
            current = copy.deepcopy(proposed)
            row = current['cross_sections'][0]
            if mode == 'interior':
                row['elevation_ft'][len(row['elevation_ft'])//2] += 1.
            elif mode == 'bank':
                row['bank_stations_ft'][0] += 1.
            elif mode == 'boundary':
                current['boundary_slopes'] = {'downstream': .02}
            elif mode == 'direction':
                row['cutline_xy'][0][1] += 1.
            elif mode == 'coefficient':
                row['expansion_contraction'] = [.5, .3]
            elif mode == 'roughness':
                row['manning_segments'] = [[0., .04]]
            else:
                row['ineffective_left'][1] += 1.
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                coverage.validate_extension(old, current, sampler, 120.)

    def test_rejects_wrong_dem_and_width(self):
        old, proposed, sampler = self.extended()
        with self.assertRaises(ValueError):
            coverage.validate_extension(old, proposed, sampler, 20.)
        sampler.sample = lambda points: np.full(len(points), np.nan)
        with self.assertRaisesRegex(ValueError, 'DEM'):
            coverage.validate_extension(old, proposed, sampler, 120.)

    def test_policy_requires_finite_explicit_bounds(self):
        self.assertEqual(coverage.controls(dict(maximum_rounds=3, maximum_width_ft=2000)), (3, 2000.))
        for rounds, width in [(True, 120), (1.5, 120), (0, 120), (6, 120), (1, float('nan')), (1, 2001), (1, None)]:
            with self.subTest(rounds=rounds, width=width), self.assertRaises(ValueError):
                coverage.controls(dict(maximum_rounds=rounds, maximum_width_ft=width))

    def test_case_paths_retain_local_imagery_and_sources(self):
        with tempfile.TemporaryDirectory(dir=coverage.ROOT) as tmp:
            folder=Path(tmp)
            source=folder/'baseline/project.json'
            save(source,dict(title='test',scenarios=[{'id':'q100'},{'id':'q200'}],
                terrain={'raster':'terrain.tif','provenance':'terrain.json'},
                delivery={'imagery':{'raster':'aerial.tif'},'additional_sources':['source.pdf']}))
            dest=folder/'batch/repair_1'
            config=coverage.case_configuration({'source_project':{'path':str(source)},'scenario_id':'q100'},dest,1)
            self.assertEqual((dest/config['delivery']['imagery']['raster']).resolve(),source.parent/'aerial.tif')
            self.assertEqual((dest/config['terrain']['raster']).resolve(),source.parent/'terrain.tif')
            self.assertEqual(config['scenarios'],[{'id':'q100'}])

    def batch(self, wet_after, limit=3, failure=False, resume=False):
        with tempfile.TemporaryDirectory(dir=coverage.ROOT) as tmp:
            folder = Path(tmp)
            plan = dict(policy=dict(maximum_rounds=limit, maximum_width_ft=120),
                        source_project={'path':'project.json'}, source_geometry={'path':'geometry.json'},
                        evidence=[{'path':'summary.json'}])
            save(folder/'project.json', {'terrain':{'vertical_unit':'ft'}})
            save(folder/'geometry.json', {'vertical_datum':'TEST', 'round':0})
            save(folder/'study.json', plan)
            save(folder/'review.json', {'confirmation':'test only'})
            preview = lambda geometry, *_: dict(geometry={'vertical_datum':'TEST','round':geometry['round']+1},
                changes=[{'rs':1}] if geometry['round'] < wet_after else [],
                wet_sections=[1] if geometry['round'] < wet_after else [])
            def run_case(sp, plan, rp, review, case, journal, path, timeout):
                record = dict(id=case['id'], status='FAILED' if failure else 'COMPUTED')
                journal['cases'].append(record)
                save(path, journal)
                return record
            with patch.object(coverage, 'ROOT', folder), \
                 patch.object(coverage, 'load_summary', return_value=(None, {'terrain':{}}, None)), \
                 patch.object(coverage, 'Sampler'), patch.object(coverage, 'proposal', side_effect=preview), \
                 patch.object(coverage, 'case_input', side_effect=lambda p, f, n, v: {'id':'repair_'+str(n)}), \
                 patch.object(coverage, 'case_evidence', return_value=(None, {'terrain':{}}, None, [])), \
                 patch.object(coverage, 'analyze', return_value={}), \
                 patch('ras_workflow.study.run_case', side_effect=run_case) as execute:
                coverage.run(folder/'study.json', plan, folder/'review.json', {}, 180)
                count = execute.call_count
                if resume:
                    original = sha(folder/'execution.json')
                    coverage.run(folder/'study.json', plan, folder/'review.json', {}, 180)
                    self.assertEqual(execute.call_count, count)
                    self.assertEqual(sha(folder/'execution.json'), original)
                return read(folder/'execution.json'), count

    def test_bounded_batch_stops_when_coverage_resolves_and_reuses_completed(self):
        journal, count = self.batch(wet_after=2, resume=True)
        self.assertEqual(count, 2)
        self.assertEqual(journal['status'], 'COVERAGE_RESOLVED_REVIEW_REQUIRED')

    def test_batch_stops_at_limit_or_failure(self):
        journal, count = self.batch(wet_after=3, limit=1)
        self.assertEqual(count, 1)
        self.assertEqual(journal['status'], 'ROUND_LIMIT_REQUIRES_REVIEW')
        journal, count = self.batch(wet_after=3, failure=True)
        self.assertEqual(count, 1)
        self.assertEqual(journal['status'], 'INCOMPLETE')

    def test_start_retry_preserves_existing_confirmation(self):
        from ras_workflow import app_study
        with tempfile.TemporaryDirectory(dir=coverage.ROOT) as tmp:
            path = Path(tmp)
            save(path/'study.json', {'case_kind':'software_validation','evidence':[{'path':'baseline'}]})
            review = {'test':'immutable existing confirmation'}
            save(path/'local_confirmation.json', review)
            model = dict(id='test', revision=1, pending_study={'path':str(path/'study.json'),'sha256':'test'}, summary={'path':'baseline'})
            with patch.object(app_study.core, 'model', return_value=model), \
                 patch.object(app_study.core, 'require_idle'), patch.object(app_study.core, 'persist'), \
                 patch.object(app_study.core, 'launch'), patch.object(app_study, 'intact', return_value=True), \
                 patch.object(app_study.study, 'reviewed') as reviewed:
                app_study.start('test', dict(revision=1, token='test', confirmed=True))
                self.assertEqual(read(path/'local_confirmation.json'), review)
                self.assertTrue(reviewed.called)

    def test_incomplete_batch_retains_retry_and_other_studies(self):
        from ras_workflow import app_study
        entry = dict(path='coverage-analysis.json', sha256='analysis')
        exports = dict(path='coverage-exports.json', sha256='exports')
        for state, delivery in [('INCOMPLETE','READY_FOR_REVIEW'), ('ROUND_LIMIT_REQUIRES_REVIEW','INCOMPLETE'),
                                ('COVERAGE_RESOLVED_REVIEW_REQUIRED','READY_FOR_REVIEW')]:
            model = dict(active_study={'study':{'path':'study.json'},'review':{'path':'review.json'}},
                         pending_study={'path':'study.json'}, latest_spacing={'path':'spacing.json'})
            with patch.object(app_study.core, 'model', return_value=model), \
                 patch.object(app_study, 'intact', return_value=True), patch.object(app_study, 'item', return_value=entry), \
                 patch.object(app_study.core, 'persist'), patch.object(coverage, 'export', return_value=exports), \
                 patch.object(app_study, 'read', return_value={'delivery':{'status':delivery}}), \
                 patch.object(app_study.study, 'run', return_value={'analysis_kind':'coverage_repair','status':state}):
                app_study.execute('test')
            self.assertEqual('pending_study' in model, state == 'INCOMPLETE' or delivery == 'INCOMPLETE')
            self.assertEqual(model['latest_spacing'], {'path':'spacing.json'})
            self.assertEqual(model['latest_coverage'], entry)

    def test_boundary_envelope_excludes_extent_repair_cases(self):
        from ras_workflow.geometry_auto_qa import boundary_study_water
        with patch('ras_workflow.report_studies.collect', return_value=([{'coverage':True,'cases':[{'id':'saved_baseline'}]}], [])):
            self.assertEqual(boundary_study_water('test', {}, {}), ({}, []))

    def test_new_extent_can_request_imagery_after_verifying_old_package(self):
        from ras_workflow import site_delivery
        from ras_workflow.common import sha
        from pyproj import CRS
        with tempfile.TemporaryDirectory(dir=coverage.ROOT) as tmp:
            package = Path(tmp)
            (package/'GIS').mkdir()
            raster = package/'GIS/Aerial.tif'
            raster.write_bytes(b'test fixture')
            receipt = dict(status='READY_FOR_MAP_REVIEW', requested_crs='EPSG:26913',
                           requested_bounds=[0,0,10,10], raster={'sha256':sha(raster)})
            with patch.object(site_delivery, 'verify') as verify, patch.object(site_delivery, 'read', return_value=receipt):
                self.assertIsNone(site_delivery.cached_imagery(package, CRS.from_epsg(26913), [0,0,20,20], True))
                self.assertTrue(verify.called)
                with self.assertRaisesRegex(ValueError, 'extent'):
                    site_delivery.cached_imagery(package, CRS.from_epsg(26913), [0,0,20,20])
                raster.write_bytes(b'changed fixture')
                with self.assertRaisesRegex(ValueError, 'hash'):
                    site_delivery.cached_imagery(package, CRS.from_epsg(26913), [0,0,20,20], True)


if __name__ == '__main__':
    unittest.main()
