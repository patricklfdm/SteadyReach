"""Bounded, nested DEM spacing trials with explicit final batch confirmation."""
import copy
import math

import numpy as np
from pyproj import CRS

from .common import ROOT, intact, item, read, save, unique_id, utc
from .geometry_qa import section_fingerprint, spatial_issues
from .section_joint import flow_crossing, repair
from .terrain_auto import Sampler
from .river import is_river


SPACING_CODES = {
    'MINIMUM_ERROR_SOLUTION', 'CRITICAL_DEPTH_FALLBACK', 'DOWNSTREAM_EGL_RISE',
    'NATIVE_ENERGY_NOT_BALANCED', 'NATIVE_LARGE_ENERGY_LOSS', 'ENERGY_BALANCE_ERROR',
    'NATIVE_VELOCITY_HEAD_CHANGE', 'NATIVE_CONVEYANCE_CHANGE',
    'NATIVE_CRITICAL_DEPTH_FALLBACK', 'NATIVE_HYDRAULIC_JUMP',
}


class IntervalUnavailable(ValueError):
    def __init__(self, a, b, reason):
        self.brackets = [[a['rs'], b['rs']]]
        super().__init__(reason)


class RefinementConflict(ValueError):
    def __init__(self, brackets):
        self.brackets = brackets
        super().__init__('Bounded direction/coverage search could not fit added cutlines between retained sections')


def intervals(geometry, issues, scope):
    if scope not in ('warnings', 'all'):
        raise ValueError('Choose warning-adjacent intervals or the entire reach')
    rows = geometry['cross_sections']
    flagged = {}
    for issue in issues:
        if issue.get('code') not in SPACING_CODES:
            continue
        try:
            station = float(issue['station'])
        except (TypeError, ValueError, KeyError):
            continue
        flagged.setdefault(station, set()).add(issue['code'])
    result = []
    for a, b in zip(rows, rows[1:]):
        reasons = sorted(flagged.get(a['rs'], set()) | flagged.get(b['rs'], set()))
        if scope == 'all' or reasons:
            result.append(dict(upstream_rs=a['rs'], downstream_rs=b['rs'], reasons=reasons,
                               channel_length_ft=a['reach_lengths_ft'][1]))
    if not result:
        raise ValueError('No spacing-related warning interval found. Review the full-reach option / 未检出加密相关警告区间，可核对全河段选项')
    return result


def refine(geometry, selected, sampler, reference_water=None):
    """Insert real DEM samples and preserve all retained hydraulic section data."""
    if not is_river(geometry):
        raise ValueError('Automatic nested spacing currently supports a continuous river reach')
    if not CRS.from_user_input(geometry['horizontal_crs']).equals(sampler.crs) or geometry['vertical_datum'] != sampler.datum:
        raise ValueError('Geometry and sampled DEM CRS/datum must match')
    rows = geometry['cross_sections']
    pairs = {(v['upstream_rs'], v['downstream_rs']) for v in selected}
    available = {(a['rs'], b['rs']) for a, b in zip(rows, rows[1:])}
    if not pairs or not pairs <= available:
        raise ValueError('Selected spacing intervals must be adjacent current sections')
    if len(rows) + len(pairs) > 500:
        raise ValueError('Spacing trial exceeds 500 sections. Select a smaller warning scope')
    lines = geometry.get('flowlines', [])
    if len(lines) != 1:
        raise ValueError('One saved continuous flowline required for spacing trials')
    line = np.asarray(lines[0]['xy'], float)
    chain = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    result = copy.deepcopy(geometry)
    refined, changes, next_intervals = [], [], []
    for a, b in zip(rows, rows[1:]):
        retained = copy.deepcopy(a)
        refined.append(retained)
        if (a['rs'], b['rs']) not in pairs:
            continue
        if any(r.get(k) for r in (a, b) for k in ('manning_segments', 'ineffective_left', 'ineffective_right')):
            raise IntervalUnavailable(a,b,'Explicit roughness/ineffective controls need a section-specific decision')
        left, right = np.asarray(a['cutline_xy'], float), np.asarray(b['cutline_xy'], float)
        if left.shape != (2, 2) or right.shape != (2, 2):
            raise IntervalUnavailable(a,b,'Spacing proposals require straight two-point cutlines')
        cut = (left + right) / 2
        locations = [flow_crossing(c, line) for c in (left, cut, right)]
        if any(v is None for v in locations) or not locations[0] < locations[1] < locations[2]:
            raise IntervalUnavailable(a,b,'Added cutline cannot have one ordered flowline crossing')
        fraction = (locations[1] - locations[0]) / (locations[2] - locations[0])
        lengths = np.asarray(a['reach_lengths_ft'], float)
        if min(fraction, 1-fraction) * lengths[1] < 2*sampler.cell_ft:
            raise IntervalUnavailable(a,b,'Refinement would be below two DEM cells in channel spacing')
        width = float(np.linalg.norm(cut[1] - cut[0]) * sampler.factor)
        bank_fractions = []
        for r in (a, b):
            start, end = r['station_ft'][0], r['station_ft'][-1]
            bank_fractions.append((np.asarray(r['bank_stations_ft']) - start) / (end-start))
        banks = np.mean(bank_fractions, axis=0) * width
        if not 0 < banks[0] < banks[1] < width:
            raise ValueError('Inferred bank stations must lie inside the new section')
        count = min(498, max(3, math.ceil(width / sampler.cell_ft) + 1))
        stations = np.unique(np.r_[np.linspace(0, width, count), banks])
        heights = sampler.sample(cut[0] + stations[:, None]/width * (cut[1]-cut[0]))
        if not np.isfinite(heights).all():
            raise IntervalUnavailable(a,b,'Added section crosses DEM NoData')
        rs = round((a['rs'] + b['rs']) / 2, 2)
        if not b['rs'] < rs < a['rs']:
            raise IntervalUnavailable(a,b,'Native two-decimal station IDs cannot represent another refinement')
        center = [float(np.interp(locations[1], chain, line[:, k])) for k in (0, 1)]
        retained['reach_lengths_ft'] = (lengths * fraction).tolist()
        new = dict(rs=rs, center_xy=center, cutline_xy=cut.tolist(),
                   station_ft=stations.tolist(), elevation_ft=heights.tolist(),
                   bank_stations_ft=banks.tolist(), reach_lengths_ft=(lengths*(1-fraction)).tolist(),
                   expansion_contraction=copy.deepcopy(a['expansion_contraction']),
                   reach_id=a.get('reach_id', 'river'), local_chainage_ft=locations[1]*sampler.factor,
                   provenance='Real DEM samples at an intermediate cutline; bank fractions inferred from adjacent confirmed sections',
                   review_status='DRAFT_REQUIRES_REVIEW', rs_basis='Nested identifier between retained sections',
                   spacing_assumptions=dict(bank_basis='Mean adjacent bank fractions',
                       loss_coefficient_basis='Upstream interval coefficients',
                       length_basis='Original LOB/channel/ROB totals partitioned at the flowline crossing'))
        sampler.stamp(new)
        refined.append(new)
        changes.append(dict(station=rs, bracket=[a['rs'], b['rs']], width_ft=width,
                            banks_ft=banks.tolist(), sampled_points=len(stations),
                            cutline_xy=cut.tolist(), station_ft=stations.tolist(), elevation_ft=heights.tolist(),
                            source=sampler.source, assumptions=new['spacing_assumptions']))
        next_intervals += [dict(upstream_rs=a['rs'], downstream_rs=rs), dict(upstream_rs=rs, downstream_rs=b['rs'])]
    refined.append(copy.deepcopy(rows[-1]))
    result.update(cross_sections=refined, approved_for_model=False, status='DRAFT_REQUIRES_REVIEW')
    water = {}
    if reference_water:
        for change in changes:
            row = next(r for r in refined if r['rs'] == change['station'])
            location = flow_crossing(row['cutline_xy'], line)
            water[row['rs']] = float(np.interp(location, [v[0] for v in reference_water],
                                             [v[1] for v in reference_water]))
            change['reference_screen_wse_ft'] = water[row['rs']]
    wet_ends = any(min(r['elevation_ft'][0], r['elevation_ft'][-1]) <= water[r['rs']]
                   for r in refined if r['rs'] in water)
    if spatial_issues(refined) or wet_ends:
        old_ids = {row['rs'] for row in rows}
        protected = [i for i, row in enumerate(refined) if row['rs'] in old_ids]
        max_width = max(2000., max(r['station_ft'][-1]-r['station_ft'][0] for r in refined))
        adjusted = repair(result, sampler, water, max_width, protected)
        result = adjusted['geometry']
        result['spacing_direction_search'] = adjusted['search']
        adjustments = {r['rs']: r for r in adjusted['changes']}
        proposed = {r['rs']: r for r in result['cross_sections']}
        for change in changes:
            row = proposed[change['station']]
            adjustment = adjustments.get(row['rs'], {})
            if row.get('bank_stations_ft') is None:
                row['bank_stations_ft'] = [v+adjustment.get('station_label_shift_ft', 0.)
                                          for v in change['banks_ft']]
            change.update(cutline_xy=row['cutline_xy'], elevation_ft=row['elevation_ft'],
                          station_ft=row['station_ft'], banks_ft=row['bank_stations_ft'],
                          width_ft=row['station_ft'][-1]-row['station_ft'][0],
                          sampled_points=len(row['station_ft']),
                          rotation_deg=adjustment.get('rotation_deg', 0.), coverage_adjustment=adjustment)
        conflicts = spatial_issues(result['cross_sections'])
        if conflicts or adjusted['unresolved']:
            involved = {result['cross_sections'][i]['rs'] for issue in conflicts for i in issue['sections']}
            involved.update(issue['rs'] for issue in adjusted['unresolved'])
            raise RefinementConflict([change['bracket'] for change in changes if change['station'] in involved])
    from .bank_review import spacing_metadata
    by_station={r['rs']:r for r in result['cross_sections']}
    for change in changes:
        row=by_station[change['station']]
        row['bank_candidates']=spacing_metadata(row,change['bracket'])
    # Old global array indices no longer describe this refined reach.
    from .bank_reach import refresh
    if result.get('bank_reach_summary'):refresh(result)
    result['spacing_trial'] = dict(changes=changes, created_utc=utc(), engineering_acceptance='NOT_ASSESSED')
    return result, changes, next_intervals


def confirm_geometry(geometry, confirmation, basis=None):
    """Called only after the existing study review has authenticated exact case files."""
    result = copy.deepcopy(geometry)
    result.update(approved_for_model=True, status='CONDITIONAL_SPACING_TRIAL')
    for row in result['cross_sections']:
        row['terrain_review'] = dict(decision='ACCEPT', policy='local_computation_v1',
            reviewer=None, basis=basis or 'Displayed nested DEM spacing and inferred banks confirmed for this conditional batch',
            fingerprint=section_fingerprint(row), confirmation=confirmation)
        if row.get('review_status') == 'DRAFT_REQUIRES_REVIEW':
            row['review_status'] = 'CONDITIONAL_BATCH_CONFIRMED'
    return result


def prepare(model, body):
    from . import app_core as core
    from .inputs import dependencies, gate, geometry_errors, load
    from .qa_review import load_summary
    from .spacing_cycle import policy
    coverage_policy = policy(body)
    path, config = load(ROOT/model['active_project'])
    scenario = next(s for s in config['scenarios'] if s['id'] == model['scenario'])
    check, geometry = gate(path, config, scenario)
    if check['status'] != 'READY_CONDITIONAL':
        raise ValueError('Baseline inputs need attention before a spacing trial')
    _, summary, hyd = load_summary(ROOT/model['summary']['path'])
    if summary['configuration'] != config:
        raise ValueError('Baseline configuration changed; compute the updated model before preparing spacing trials')
    diagnostic_entry = hyd.get('diagnostics')
    if not diagnostic_entry or not intact([diagnostic_entry]):
        raise ValueError('Verified baseline diagnostics required')
    diagnostic = read(ROOT/diagnostic_entry['path'])
    if summary.get('native_supplement'):
        from .app_outputs import validate, diagnostics
        diagnostic = diagnostics(hyd, validate(summary['native_supplement']))
    from .result_atlas import native_rows
    from .spacing_selection import recommend, eligible, limit_candidates
    if hyd.get('unit') != 'international ft':
        raise ValueError('Spacing selection requires verified international-foot outputs')
    ranked, selection = recommend(geometry, diagnostic['issues'], native_rows(hyd), SPACING_CODES)
    scope = body.get('scope', 'automatic')
    valid_issues = [v for v in diagnostic['issues'] if v not in selection['unlocated_spacing_issues']]
    candidates = ranked if scope == 'automatic' else intervals(geometry, valid_issues, scope)
    sampler = Sampler(summary['terrain'], config['terrain']['vertical_unit'], geometry['vertical_datum'])
    candidates, excluded = eligible(geometry, candidates, sampler.cell_ft)
    selection.update(scope=scope, candidate_intervals=len(candidates)+len(excluded), maximum_intervals=body.get('maximum_intervals', 12))
    if scope == 'automatic':
        selected, deferred = limit_candidates(geometry, candidates, selection['maximum_intervals'])
    else:
        selected, deferred = candidates, []
    from .qa import verified_profiles
    profiles = verified_profiles(hyd)
    level_by_station = {float(rs): max(p[rs] for p in profiles.values())
                        for rs in next(iter(profiles.values()))}
    line = geometry['flowlines'][0]['xy']
    reference_water = [(flow_crossing(row['cutline_xy'], line), level_by_station[row['rs']])
                       for row in geometry['cross_sections']]
    if (any(at is None for at, _ in reference_water)
            or any(a[0] >= b[0] for a, b in zip(reference_water, reference_water[1:]))):
        raise ValueError('Baseline flowline crossings must be unique and ordered for the water-level coverage screen')
    variants = []
    while selected:
        variants = [('baseline', geometry, [])]
        current, targets = geometry, selected
        try:
            for level in (1, 2):
                current, changes, targets = refine(current, targets, sampler, reference_water)
                validation = confirm_geometry(current, dict(status='VALIDATION_ONLY_NOT_AUTHORIZATION'))
                errors = geometry_errors(validation, config['case_kind'] == 'software_validation')
                if errors:
                    raise ValueError('Spacing candidate invalid: ' + '; '.join(errors))
                variants.append(('refinement_' + str(level), current, changes))
            break
        except (RefinementConflict, IntervalUnavailable) as error:
            omitted = [v for v in selected
                       if any(v['upstream_rs'] >= a > b >= v['downstream_rs'] for a, b in error.brackets)]
            if not omitted:
                raise
            excluded.extend(dict(v, reason=str(error), reason_code='DEM_OR_LAYOUT_CONSTRAINT') for v in omitted)
            selected = [v for v in selected if v not in omitted]
            if scope == 'automatic' and deferred:
                refill = [{k:v for k,v in row.items() if k != 'reason_code'} for row in deferred]
                selected, deferred = limit_candidates(geometry, selected + refill, selection['maximum_intervals'])
    if not selected:
        variants = []
    import os
    folder = core.folder(model['id'])/'studies'/unique_id()/'prepared'
    folder.mkdir(parents=True)
    specification = dict(type='section_spacing', scope=scope, selection=selection, deferred_intervals=deferred,
                         intervals=selected, excluded_intervals=excluded,
                         purpose='Two nested real DEM refinements at fixed flow, boundary, roughness and retained profiles',
                         source=model['summary'], warning_coverage=diagnostic['warning_coverage'],
                         coverage_screen='Maximum baseline profile WSE interpolated along the saved flowline; fresh computations still required',
                         maximum_new_width_ft=max(2000.,max(r['station_ft'][-1]-r['station_ft'][0] for r in geometry['cross_sections'])))
    if coverage_policy:
        specification['coverage_policy'] = coverage_policy
    save(folder/'specification.json', specification)
    cases = []
    for name, variant, changes in variants:
        dest = folder/'cases'/name
        c = copy.deepcopy(config)
        c.update(title=config['title']+' / '+name, geometry='geometry.json', authorization=None,
                 geometry_review='Exact nested spacing cases await the displayed batch confirmation', scenarios=[copy.deepcopy(scenario)])
        c.setdefault('delivery', {})['enabled'] = False
        for field in ('reference_results', 'benchmark_preparation', 'configuration_approval'):
            c.pop(field, None)
        for field in ('raster', 'provenance'):
            if c['terrain'].get(field):
                c['terrain'][field] = os.path.relpath((path.parent/c['terrain'][field]).resolve(), dest)
        save(dest/'geometry.json', variant)
        save(dest/'project.draft.json', c)
        case_changes = []
        if name != 'baseline':
            case_changes.append(dict(path='cross_sections', before=len(geometry['cross_sections']),
                                     after=len(variant['cross_sections']),
                                     basis='Nested fresh DEM sections with displayed inferred banks'))
        cases.append(dict(id=name, topic='section_spacing', changes=case_changes, added_sections=changes,
                          section_count=len(variant['cross_sections']), draft=item(dest/'project.draft.json'),
                          geometry=item(dest/'geometry.json')))
    plan = dict(schema_version='1.0', id='section_spacing', analysis_kind='section_spacing',
                scope=specification['scope'],
                status='DRAFT_REQUIRES_REVIEW' if selected else 'NO_ELIGIBLE_INTERVALS', project_id=config['project_id'], case_kind=config['case_kind'],
                scenario_id=model['scenario'], created_utc=utc(), specification=item(folder/'specification.json'),
                source_inputs=dependencies(path, config), evidence=[model['summary'], diagnostic_entry, hyd['raw_hdf'], hyd['raw_controller']] + ([summary['native_supplement']] if summary.get('native_supplement') else []),
                intervals=selected, excluded_intervals=excluded, deferred_intervals=deferred, selection=selection, cases=cases,
                measurement_topics=[], engineering_acceptance='NOT_ASSESSED')
    if coverage_policy:
        plan['coverage_policy'] = coverage_policy
    plan['map_geometry'] = dict(flowline=line, retained=[dict(rs=r['rs'], cutline_xy=r['cutline_xy'])
                                                      for r in geometry['cross_sections']])
    save(folder/'study.json', plan)
    model['pending_study'] = item(folder/'study.json')
    core.persist(model, 'PREPARE_SPACING', dict(study=model['pending_study']))
    return dict(token=model['pending_study']['sha256'], entry=model['pending_study'], plan=plan)
