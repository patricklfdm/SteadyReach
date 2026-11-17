"""Confirmed, bounded wet-end repair batches driven by each actual computation."""
import copy
import os

import numpy as np
from pyproj import CRS

from .common import ROOT, intact, item, lock, read, save, unique_id, utc
from .geometry_qa import spatial_issues
from .inputs import dependencies, gate, load
from .qa_review import load_summary
from .river import is_river
from .section_joint import repair
from .terrain_auto import Sampler


def controls(policy):
    rounds = policy.get('maximum_rounds')
    width = policy.get('maximum_width_ft')
    if type(rounds) is not int or not 1 <= rounds <= 5:
        raise ValueError('Choose one to five actual repair calculations / 请选择 1–5 轮修订计算')
    if type(width) not in (int, float) or not 120 <= width <= 2000:
        raise ValueError('Choose a total section-width bound of 120–2000 ft / 总断面宽度上限为 120–2000 ft')
    return rounds, float(width)


def validate_extension(previous, current, sampler, maximum):
    """Independently enforce the confirmed extent-only changes and real DEM samples."""
    if {k: v for k, v in previous.items() if k != 'cross_sections'} != {
            k: v for k, v in current.items() if k != 'cross_sections'}:
        raise ValueError('Coverage repair changed a reach-level hydraulic control')
    if len(previous['cross_sections']) != len(current['cross_sections']):
        raise ValueError('Coverage repair changed the section count')
    changed_keys = {'station_ft', 'elevation_ft', 'cutline_xy', 'bank_stations_ft',
                    'ineffective_left', 'ineffective_right', 'terrain_sampling', 'terrain_review'}
    for old, new in zip(previous['cross_sections'], current['cross_sections']):
        if old == new:
            continue
        if {k: v for k, v in old.items() if k not in changed_keys} != {
                k: v for k, v in new.items() if k not in changed_keys}:
            raise ValueError('Coverage repair changed a section control')
        if old.get('manning_segments'):
            raise ValueError('Explicit roughness subdivisions require exterior material review')
        a, b = np.asarray(old['cutline_xy'], float)
        c, d = np.asarray(new['cutline_xy'], float)
        direction = (b-a)/np.linalg.norm(b-a)
        left, right = float(np.dot(a-c, direction)), float(np.dot(d-b, direction))
        if min(left, right) < -1e-8 or not np.allclose(c, a-left*direction, atol=1e-8, rtol=0) or not np.allclose(d, b+right*direction, atol=1e-8, rtol=0):
            raise ValueError('Coverage repair rotated or shortened a cutline')
        x, z = np.asarray(new['station_ft']), np.asarray(new['elevation_ft'])
        shift = left*sampler.factor-old['station_ft'][0]
        start = int(np.argmin(abs(x-(old['station_ft'][0]+shift))))
        stop = start+len(old['station_ft'])
        if stop > len(x) or not np.allclose(x[start:stop], np.asarray(old['station_ft'])+shift, atol=1e-7, rtol=0) or not np.array_equal(z[start:stop], old['elevation_ft']):
            raise ValueError('Original interior station/elevation samples changed')
        if len(x) > 500 or x[-1]-x[0] > maximum+1e-6:
            raise ValueError('Coverage repair exceeded the confirmed point/width bound')
        if not np.isclose(x[-1]-x[0], np.linalg.norm(d-c)*sampler.factor, atol=1e-6, rtol=0):
            raise ValueError('New station width differs from the spatial cutline')
        if not np.allclose(new['bank_stations_ft'], np.asarray(old['bank_stations_ft'])+shift, atol=1e-7, rtol=0):
            raise ValueError('Coverage repair moved a bank in plan')
        for key in ('ineffective_left', 'ineffective_right'):
            expected = copy.deepcopy(old.get(key))
            if expected:
                expected[0] += shift
            if new.get(key) != expected:
                raise ValueError('Coverage repair changed ineffective-area controls')
        exterior = np.r_[np.arange(start), np.arange(stop, len(x))]
        points = c+(x[exterior]-x[0])[:, None]/sampler.factor*direction
        heights = sampler.sample(points)
        if not np.isfinite(heights).all() or not np.allclose(heights, z[exterior], atol=1e-6, rtol=0):
            raise ValueError('Exterior elevations differ from the confirmed DEM')
    if spatial_issues(current['cross_sections']):
        raise ValueError('Coverage repair created a spatial conflict')


def proposal(geometry, summary, sampler, maximum):
    from .qa_locator import collect
    if not is_river(geometry):
        raise ValueError('Automatic coverage batches currently support continuous river reaches')
    if not sampler.crs.equals(CRS.from_user_input(geometry['horizontal_crs'])) or sampler.datum != geometry['vertical_datum']:
        raise ValueError('Coverage batch DEM and geometry CRS/datum must match')
    water = {}
    for row in collect(summary['hydraulics'])['rows']:
        if row['left_excess_ft'] > 0 or row['right_excess_ft'] > 0:
            station = float(row['rs'])
            water[station] = max(water.get(station, float('-inf')), row['wse_ft'])
    result = repair(geometry, sampler, water, maximum, allow_rotation=False)
    validate_extension(geometry, result['geometry'], sampler, maximum)
    result.update(wet_sections=sorted(water, reverse=True),
                  water_levels_ft={str(key): value for key, value in water.items()})
    return result


def prepare(model, body):
    from . import app_core as core
    policy = dict(maximum_rounds=body.get('maximum_rounds'), maximum_width_ft=body.get('maximum_width_ft'))
    controls(policy)
    path, config = load(ROOT/model['active_project'])
    scenario = next(s for s in config['scenarios'] if s['id'] == model['scenario'])
    check, geometry = gate(path, config, scenario)
    if check['status'] != 'READY_CONDITIONAL':
        raise ValueError('Baseline inputs need attention before a coverage batch')
    _, summary, _ = load_summary(ROOT/model['summary']['path'])
    if summary['configuration'] != config:
        raise ValueError('Coverage baseline configuration changed after computation')
    sampler = Sampler(summary['terrain'], config['terrain']['vertical_unit'], geometry['vertical_datum'])
    preview = proposal(geometry, summary, sampler, policy['maximum_width_ft'])
    folder = core.folder(model['id'])/'studies'/unique_id()/'prepared'
    save(folder/'initial_preview.json', preview)
    save(folder/'specification.json', dict(type='coverage_repair', **policy,
        method='Fixed-direction DEM exterior extension with preserved interior samples and bank plan positions',
        stop_conditions=['No wet section ends', 'No feasible extension', 'Round limit', 'Failed computation or changed evidence'],
        interpretation='New exterior material retains the existing overbank roughness assumption. Floodplain connectivity and other hydraulic findings require review.'))
    plan = dict(schema_version='1.0', id='coverage_repair', analysis_kind='coverage_repair',
        project_id=config['project_id'], scenario_id=model['scenario'], case_kind=config['case_kind'],
        status='DRAFT_REQUIRES_REVIEW', created_utc=utc(), policy=policy,
        source_project=item(path), source_geometry=item(path.parent/config['geometry']),
        initial_preview=item(folder/'initial_preview.json'), specification=item(folder/'specification.json'),
        source_inputs=dependencies(path, config), evidence=[model['summary'], item(folder/'initial_preview.json')],
        cases=[], measurement_topics=[], engineering_acceptance='NOT_ASSESSED')
    save(folder/'study.json', plan)
    model['pending_study'] = item(folder/'study.json')
    core.persist(model, 'PREPARE_COVERAGE_BATCH', dict(study=model['pending_study']))
    return dict(token=model['pending_study']['sha256'], entry=model['pending_study'], plan=plan, preview=preview)


def case_configuration(plan, dest, number):
    source = ROOT/plan['source_project']['path']
    config = read(source)
    config.update(title=config['title']+' / coverage repair '+str(number), geometry='geometry.json', authorization=None)
    config['scenarios'] = [s for s in config['scenarios'] if s['id'] == plan['scenario_id']]
    config.setdefault('delivery', {})['enabled'] = False
    for field in ('reference_results', 'benchmark_preparation', 'configuration_approval', 'section_workflow'):
        config.pop(field, None)
    for field in ('raster', 'provenance'):
        if config['terrain'].get(field):
            config['terrain'][field] = os.path.relpath((source.parent/config['terrain'][field]).resolve(), dest)
    config['delivery']['additional_sources'] = [os.path.relpath((source.parent/p).resolve(), dest)
                                               for p in config['delivery'].get('additional_sources', [])]
    imagery = config['delivery'].get('imagery', {})
    if imagery.get('raster'):
        imagery['raster'] = os.path.relpath((source.parent/imagery['raster']).resolve(), dest)
    return config


def case_input(plan, folder, number, preview):
    dest = folder/'cases'/('repair_'+str(number))
    config = case_configuration(plan, dest, number)
    for name, content in [('project.draft.json', config), ('geometry.json', preview['geometry']), ('proposal.json', preview)]:
        path = dest/name
        if path.exists() and read(path) != content:
            raise ValueError('Prepared coverage step changed; prepare a fresh batch')
        if not path.exists():
            save(path, content)
    return dict(id='repair_'+str(number), draft=item(dest/'project.draft.json'),
                geometry=item(dest/'geometry.json'), proposal=item(dest/'proposal.json'),
                section_count=len(preview['geometry']['cross_sections']))


def case_evidence(case, record, plan, review_path):
    if record.get('status') != 'COMPUTED' or not intact([record['summary'], case['draft'], case['geometry'], case['proposal']]):
        raise ValueError('Coverage computation evidence is incomplete or changed')
    path, summary, hyd = load_summary(ROOT/record['summary']['path'])
    config_path = (ROOT/case['draft']['path']).parent/'project.json'
    config = read(config_path)
    if config != summary['configuration']:
        raise ValueError('Coverage case configuration differs from its computation')
    number = int(case['id'].removeprefix('repair_'))
    expected = case_configuration(plan, config_path.parent, number)
    confirmation = read(review_path)
    expected.update(geometry='geometry.confirmed.json', authorization='authorization.json',
                    geometry_review=confirmation['basis'])
    if config != expected:
        raise ValueError('Coverage case changed a confirmed configuration control')
    from .section_spacing import confirm_geometry
    expected_geometry = confirm_geometry(read(ROOT/case['geometry']['path']), item(review_path),
                                         basis=confirmation['basis'])
    if read(config_path.parent/config['geometry']) != expected_geometry:
        raise ValueError('Coverage computed geometry differs from its permitted extension')
    manifest_path = (ROOT/hyd['raw_hdf']['path']).parent.parent/'manifest.json'
    manifest = read(manifest_path)
    if manifest['source_inputs'] != dependencies(config_path, config):
        raise ValueError('Coverage case source inputs changed')
    bound = manifest['source_inputs']+manifest['input_snapshots']+manifest['native_before']+manifest['outputs']
    if not intact(bound):
        raise ValueError('Coverage native evidence changed')
    return path, summary, hyd, [record['summary'], item(manifest_path), case['draft'], case['geometry'], case['proposal']]+bound


def run(sp, plan, rp, review, timeout):
    from .study import run_case
    rounds, maximum = controls(plan['policy'])
    folder = sp.parent
    with lock(folder/'study.lock'):
        path = folder/'execution.json'
        journal = read(path) if path.exists() else dict(study=item(sp), review=item(rp), cases=[], prepared_cases=[], started_utc=utc())
        if journal['study'] != item(sp) or journal['review'] != item(rp):
            raise ValueError('Coverage batch confirmation changed')
        if journal.get('status') in ('COVERAGE_RESOLVED_REVIEW_REQUIRED', 'ROUND_LIMIT_REQUIRES_REVIEW', 'GEOMETRY_REVIEW_REQUIRED'):
            return analyze(sp, rp)
        journal.update(status='IN_PROGRESS')
        save(path, journal)
        config = read(ROOT/plan['source_project']['path'])
        geometry = read(ROOT/plan['source_geometry']['path'])
        _, summary, _ = load_summary(ROOT/plan['evidence'][0]['path'])
        sampler = Sampler(summary['terrain'], config['terrain']['vertical_unit'], geometry['vertical_datum'])
        for number in range(1, rounds+2):
            preview = proposal(geometry, summary, sampler, maximum)
            if not preview['wet_sections']:
                journal['status'] = 'COVERAGE_RESOLVED_REVIEW_REQUIRED'
                break
            if number > rounds:
                journal['status'] = 'ROUND_LIMIT_REQUIRES_REVIEW'
                break
            if not preview['changes']:
                journal['status'] = 'GEOMETRY_REVIEW_REQUIRED'
                break
            case = case_input(plan, folder, number, preview)
            existing = next((c for c in journal['prepared_cases'] if c['id'] == case['id']), None)
            if existing and existing != case:
                raise ValueError('Coverage prepared case identity changed')
            if not existing:
                journal['prepared_cases'].append(case)
                save(path, journal)
            record = next((r for r in journal['cases'] if r['id'] == case['id']), None)
            if not record or record['status'] != 'COMPUTED':
                record = run_case(sp, plan, rp, review, case, journal, path, timeout)
            if record['status'] != 'COMPUTED':
                journal['status'] = 'INCOMPLETE'
                break
            _, summary, _, _ = case_evidence(case, record, plan, rp)
            geometry = preview['geometry']
        journal.update(finished_utc=utc(), final_preview=preview)
        save(path, journal)
    return analyze(sp, rp)


def analyze(study_path, review_path, save_result=True):
    from .study import reviewed
    from .app_revision import _diagnostic_summary
    from .qa import compare
    sp, plan, rp, _ = reviewed(study_path, review_path)
    journal_path = sp.parent/'execution.json'
    journal = read(journal_path)
    if journal['study'] != item(sp) or journal['review'] != item(rp):
        raise ValueError('Coverage execution identity changed')
    _, maximum = controls(plan['policy'])
    _, summary, _ = load_summary(ROOT/plan['evidence'][0]['path'])
    geometry = read(ROOT/plan['source_geometry']['path'])
    config = read(ROOT/plan['source_project']['path'])
    sampler = Sampler(summary['terrain'], config['terrain']['vertical_unit'], geometry['vertical_datum'])
    source = plan['evidence'][0]
    baseline = source
    manifest_path = (ROOT/summary['hydraulics']['raw_hdf']['path']).parent.parent/'manifest.json'
    manifest = read(manifest_path)
    sources = [source, summary['hydraulic_results'], item(manifest_path)]
    sources += manifest['source_inputs']+manifest['input_snapshots']+manifest['native_before']+manifest['outputs']
    if not intact(sources) or summary['configuration'] != config:
        raise ValueError('Coverage baseline evidence changed')
    rows, comparisons = [], []
    records = {r['id']: r for r in journal['cases']}
    initial = proposal(geometry, summary, sampler, maximum)
    rows.append(dict(id='saved_baseline', summary=source, reused_baseline=True,
                     wet_sections=initial['wet_sections'], diagnostics=_diagnostic_summary(summary),
                     section_count=len(geometry['cross_sections'])))
    for number, case in enumerate(journal['prepared_cases'], 1):
        if case['id'] != 'repair_'+str(number) or number > plan['policy']['maximum_rounds']:
            raise ValueError('Coverage cases exceed the confirmed sequence')
        expected = proposal(geometry, summary, sampler, maximum)
        if not intact([case['draft'], case['geometry'], case['proposal']]):
            raise ValueError('Coverage prepared case changed')
        if read(ROOT/case['proposal']['path']) != expected or read(ROOT/case['geometry']['path']) != expected['geometry']:
            raise ValueError('Coverage proposal differs from the permitted actual-water repair')
        sources += [case['draft'], case['geometry'], case['proposal']]
        record = records[case['id']]
        if record['status'] != 'COMPUTED':
            rows.append(dict(id=case['id'], status=record['status'], error=record.get('error')))
            break
        path, summary, _, evidence = case_evidence(case, record, plan, rp)
        current = item(path)
        comparison = compare(source['path'], current['path'], None)
        comparisons.append(dict(case=case['id'], **comparison))
        geometry = expected['geometry']
        next_preview = proposal(geometry, summary, sampler, maximum)
        rows.append(dict(id=case['id'], status='COMPUTED', summary=current,
                         section_count=len(geometry['cross_sections']), changes=expected['changes'],
                         wet_sections=next_preview['wet_sections'], diagnostics=_diagnostic_summary(summary),
                         max_wse_change_ft=max((r['max_matched_xs_delta_wse_ft'] for r in comparison['rows']), default=None)))
        sources += evidence
        source = current
    final = proposal(geometry, summary, sampler, maximum)
    failed = [r['id'] for r in rows if r.get('status') in ('FAILED', 'BLOCKED', 'IN_PROGRESS')]
    if failed:
        status = 'INCOMPLETE'
    elif not final['wet_sections']:
        status = 'COVERAGE_RESOLVED_REVIEW_REQUIRED'
    elif len(journal['prepared_cases']) >= plan['policy']['maximum_rounds']:
        status = 'ROUND_LIMIT_REQUIRES_REVIEW'
    elif not final['changes']:
        status = 'GEOMETRY_REVIEW_REQUIRED'
    else:
        raise ValueError('Coverage execution stopped before a confirmed stop condition')
    if journal['status'] != status:
        raise ValueError('Coverage stop status differs from the actual outputs')
    result = dict(analysis_kind='coverage_repair', status=status, study=item(sp), review=item(rp),
                  execution=item(journal_path), policy=plan['policy'], baseline=baseline, final_summary=source,
                  cases=rows, failed_cases=failed, comparisons=comparisons, remaining=final['unresolved'],
                  search=final['search'], evidence=sources, hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED')
    if save_result:
        save(sp.parent/'analysis.json', result)
    return result


def export(result, model):
    from .report import generate as report_generate
    from .site_delivery import generate as delivery_generate
    folder = (ROOT/result['study']['path']).parent/'exports'/unique_id()
    summary = ROOT/result['final_summary']['path']
    report_generate(summary, folder/'reports')
    previous = model.get('latest_delivery') or model.get('previous_delivery')
    if not previous and model.get('engine_state'):
        previous = read(ROOT/model['engine_state']).get('delivery')
    reuse = previous.get('complete', {}).get('path') if previous and previous.get('mapped') else None
    delivery = delivery_generate(summary, folder/'delivery', reuse_package=reuse, refresh_imagery_extent=True)
    from .common import rel
    record = dict(analysis=item((ROOT/result['study']['path']).parent/'analysis.json'),
                  reports=rel(folder/'reports'), delivery=delivery)
    save(folder/'exports.json', record)
    return item(folder/'exports.json')
