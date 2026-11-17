"""Explicit, reviewed parameter studies; no automatic uncertainty bounds."""
import copy
import csv
import os

from .common import ROOT, finite, intact, item, lock, read, rel, safe_path, save, sha, utc, identifier, unique_id
from .inputs import dependencies, gate, geometry_errors, load
from .qa import compare, THRESHOLDS
from .river import is_river, boundary_errors

SCENARIO_FIELDS = {'channel_n', 'overbank_n', 'culvert_n'}
GROUP_FIELDS = {'span_ft', 'rise_ft', 'length_ft', 'us_invert_ft', 'ds_invert_ft',
                'entrance_loss', 'exit_loss', 'chart_scale', 'inlet_description',
                'mann_top', 'mann_bottom', 'bottom_n_depth_ft', 'depth_blocked_ft',
                'blockage_basis', 'count', 'centers_ft', 'distance_us_ft'}


def apply_changes(geometry, scenario, changes, case_kind):
    g, s = copy.deepcopy(geometry), copy.deepcopy(scenario)
    if not isinstance(changes, list) or not changes:
        raise ValueError('Each variant requires explicit changes')
    seen = set(); records = []
    for change in changes:
        path = change.get('path', ''); parts = path.split('.')
        if path in seen: raise ValueError('Duplicate parameter path')
        seen.add(path)
        if not change.get('basis') or 'value' not in change or change['value'] is None:
            raise ValueError('Explicit non-null value and basis required for every change')
        if len(parts) == 2 and parts[0] == 'scenario' and parts[1] in SCENARIO_FIELDS:
            parent, field = s, parts[1]
        elif len(parts) == 2 and parts[0] == 'boundary_slopes' and parts[1] in ['upstream', 'downstream']:
            if is_river(g) and (g.get('boundaries',{}).get(parts[1],{}).get('type')!='normal_depth' or parts[1]=='upstream' and g.get('flow_regime')=='subcritical'):
                raise ValueError('This plan does not use the selected normal-depth boundary')
            parent, field = g['boundary_slopes'], parts[1]
        elif len(parts)==4 and parts[:3]==['boundaries','downstream','stages_ft'] and parts[3].isdigit() and is_river(g):
            boundary=g.get('boundaries',{}).get('downstream',{})
            if boundary.get('type')!='known_stage':raise ValueError('This plan does not use known downstream WSE')
            parent,field=boundary['stages_ft'],int(parts[3])
            if field>=len(parent) or not finite(change['value']):raise ValueError('Invalid downstream profile or WSE')
        elif len(parts) == 3 and parts[0] == 'groups' and parts[1].isdigit() and parts[2] in GROUP_FIELDS:
            index = int(parts[1])
            if index >= len(g['structure']['groups']): raise ValueError('Unknown culvert group')
            parent, field = g['structure']['groups'][index], parts[2]
            parent['evidence_class'] = 'synthetic' if case_kind == 'software_validation' else 'assumed'
        else:
            raise ValueError('Unsupported study parameter: ' + path)
        before = copy.deepcopy(parent[field] if isinstance(parent,list) else parent.get(field)); parent[field] = copy.deepcopy(change['value'])
        records.append(dict(path=path, before=before, after=change['value'], basis=change['basis']))
    if all(r['before'] == r['after'] for r in records): raise ValueError('Variant does not change any parameter')
    errors = geometry_errors(g, case_kind == 'software_validation')
    if is_river(g):errors+=boundary_errors(g,len(s.get('profiles',[])))
    for field in (SCENARIO_FIELDS-{'culvert_n'} if is_river(g) else SCENARIO_FIELDS):
        if not finite(s.get(field)) or not 0 < s[field] < 1: errors.append('Invalid ' + field)
    if errors: raise ValueError('Invalid study variant: ' + '; '.join(errors))
    return g, s, records


def prepare(project, scenario_id, specification, output):
    path, config = load(project); spec_path = safe_path(ROOT, specification); spec = read(spec_path)
    if config.get('native_project'): raise ValueError('Parameter studies currently require explicit builder geometry')
    scenario = next((s for s in config['scenarios'] if s['id'] == scenario_id), None)
    if scenario is None: raise ValueError('Unknown baseline scenario')
    check, geometry = gate(path, config, scenario)
    if check['status'] != 'READY_CONDITIONAL': raise ValueError('Baseline input gate: ' + str(check['blocking_items']))
    kind = spec.get('case_kind')
    if kind not in ['site_conditional', 'software_validation']: raise ValueError('Explicit study case_kind required')
    if config['case_kind'] == 'software_validation' and kind != 'software_validation':
        raise ValueError('Software validation inputs cannot become site results')
    identifier(spec['id'])
    if not spec.get('purpose') or not spec.get('sources') or not intact(spec['sources']):
        raise ValueError('Study purpose and intact source evidence required')
    topics = spec.get('measurement_topics', []); cases = spec.get('cases', [])
    topic_ids = [identifier(t['id']) for t in topics]; case_ids = [identifier(c['id']) for c in cases]
    if not topics or not cases or len(set(topic_ids)) != len(topic_ids) or len(set(case_ids)) != len(case_ids) or 'baseline' in case_ids:
        raise ValueError('Unique measurement topics and non-baseline cases required')
    for t in topics:
        if not t.get('measurement_action') or not t.get('evidence_status') or not t.get('range_basis'):
            raise ValueError('Every measurement topic needs evidence status, range basis and action')
    prepared = [('baseline', copy.deepcopy(geometry), copy.deepcopy(scenario), [], None)]
    for c in cases:
        if c.get('topic') not in topic_ids: raise ValueError('Unknown measurement topic')
        g, s, changes = apply_changes(geometry, scenario, c.get('changes'), kind)
        prepared.append((c['id'], g, s, changes, c['topic']))
    folder = safe_path(ROOT, output); folder.mkdir(parents=True, exist_ok=False)
    source_inputs = dependencies(path, config); rows = []
    for name, g, s, changes, topic in prepared:
        dest = folder/'cases'/name; dest.mkdir(parents=True)
        c = copy.deepcopy(config); c['case_kind'] = kind
        c['title'] = config['title'] + ' / ' + name
        if spec.get('delivery_enabled') is False:c.setdefault('delivery',{})['enabled']=False
        for key in ['reference_results', 'benchmark_preparation', 'configuration_approval']: c.pop(key, None)
        for key in ['raster', 'provenance']:
            if c['terrain'].get(key):
                c['terrain'][key] = os.path.relpath(safe_path(path.parent, c['terrain'][key]), dest)
        c.update(geometry='geometry.json', authorization=None,
                 geometry_review='Parameter study draft; approval must bind study and all exact case files', scenarios=[s])
        s['parameter_source'] = 'Explicit study specification: ' + rel(spec_path)
        g.setdefault('limitations', []).append('Conditional parameter study; ranges do not establish measured accuracy')
        g['parameter_study'] = dict(specification=item(spec_path), case=name, changes=changes, case_kind=kind)
        save(dest/'geometry.json', g); save(dest/'project.draft.json', c)
        rows.append(dict(id=name, topic=topic, changes=changes, draft=item(dest/'project.draft.json'), geometry=item(dest/'geometry.json')))
    plan = dict(schema_version='1.0', status='DRAFT_REQUIRES_REVIEW', id=spec['id'], project_id=config['project_id'],
                case_kind=kind, scenario_id=scenario_id, created_utc=utc(), specification=item(spec_path),
                source_inputs=source_inputs, evidence=spec['sources'], measurement_topics=topics, cases=rows,
                engineering_acceptance='NOT_ASSESSED')
    save(folder/'study.json', plan)
    save(folder/'review.template.json', dict(study_sha256=sha(folder/'study.json'), decision='PENDING',
         reviewer=None, basis=None, approved_case_kind=kind, engineering_acceptance='NOT_ASSESSED'))
    return folder/'study.json'


def reviewed(study_path, review_path):
    study_path, review_path = [safe_path(ROOT, p) for p in [study_path, review_path]]
    study, review = read(study_path), read(review_path)
    if review.get('study_sha256') != sha(study_path): raise ValueError('Review does not match study hash')
    local=review.get('policy')=='local_computation_v1' and review.get('confirmed') is True and review.get('reviewer') is None
    if review.get('decision') != 'APPROVE_CONDITIONAL_STUDY' or (not local and not review.get('reviewer')) or not review.get('basis'):
        raise ValueError('Explicit named study review and basis required')
    if review.get('approved_case_kind') != study['case_kind']: raise ValueError('Review case_kind mismatch')
    entries = [study['specification']] + study['source_inputs'] + study['evidence']
    entries += [c[k] for c in study['cases'] for k in ['draft', 'geometry']]
    if not intact(entries): raise ValueError('Study source or prepared case changed; review again')
    return study_path, study, review_path, review


def report_retry_candidate(record):
    errors=record.get('errors') or []
    return bool(record.get('status')=='FAILED' and record.get('summary') and errors
                and all(str(e).startswith('Report:') for e in errors))


def verified_case(record, project, config):
    """Authenticate a saved computation independently of the current code/cache key."""
    from .qa_review import load_summary
    if not intact([record['summary']]):raise ValueError('Completed case summary changed')
    path,summary,hyd=load_summary(ROOT/record['summary']['path'])
    if summary['configuration']!=config or summary.get('errors'):
        raise ValueError('Completed case configuration or solver checkpoint differs')
    manifest=read((ROOT/hyd['raw_hdf']['path']).parent.parent/'manifest.json')
    if manifest['source_inputs']!=dependencies(project,config) or not intact(
            manifest['source_inputs']+manifest['input_snapshots']+manifest['native_before']+manifest['outputs']):
        raise ValueError('Completed case inputs or native evidence changed')
    return path, summary, hyd


def recover_case_reports(record, project, config):
    """Write a separate report edition; never overwrite or rerun native evidence."""
    from . import report
    path, summary, hyd = verified_case(record, project, config)
    folder=path.parent/('reports_retry_'+unique_id())
    result=report.generate(path,folder)
    receipt=dict(status='REPORTS_REGENERATED',summary=record['summary'],reports=item(folder/'report_manifest.json'),
        prior_failure=record,solver_started=False,run_id=hyd['run_id'],created_utc=utc(),
        visual_review=result.get('visual_review','PENDING_HUMAN_PAGE_REVIEW'))
    save(folder/'recovery.json',receipt)
    return item(folder/'recovery.json')


def run_case(sp, study, rp, review, case, journal, journal_path, timeout):
    """Execute one source-bound case and persist its progress through normal CLI entry."""
    from .cli import execute
    dest = (ROOT/case['draft']['path']).parent; c = read(ROOT/case['draft']['path'])
    geometry_hash=case['geometry']['sha256']
    if study.get('analysis_kind') in ('section_spacing','coverage_repair'):
        from .section_spacing import confirm_geometry
        geometry=confirm_geometry(read(ROOT/case['geometry']['path']),item(rp),
                basis=review['basis'] if study.get('analysis_kind')=='coverage_repair' else None)
        target=dest/'geometry.confirmed.json'
        if target.exists() and read(target)!=geometry:raise ValueError('Confirmed spacing geometry changed')
        if not target.exists():save(target,geometry)
        c['geometry']=target.name;geometry_hash=sha(target)
    c['authorization'] = 'authorization.json'; c['geometry_review'] = review['basis']
    auth = dict(project_id=study['project_id'], allowed_geometry_sha256=geometry_hash,
                scope=study['case_kind'], study=item(sp), review=item(rp), authority=review['reviewer'], basis=review['basis'])
    for name, content in [('authorization.json', auth), ('project.json', c)]:
        p = dest/name
        if p.exists() and read(p) != content: raise ValueError('Approved study configuration changed: ' + rel(p))
        if not p.exists(): save(p, content)
    previous=next((r for r in journal['cases'] if r['id']==case['id']),{})
    resume_native = (previous.get('status') == 'COMPUTED' or report_retry_candidate(previous)
                     or previous.get('resume_native') is True)
    record = dict(id=case['id'], status='IN_PROGRESS', started_utc=utc())
    if previous:
        journal.setdefault('attempt_history', []).append(copy.deepcopy(previous))
    if resume_native:
        record.update(summary=previous['summary'], resume_native=True, solver_started=False)
    journal['cases'] = [r for r in journal['cases'] if r['id'] != case['id']] + [record]; save(journal_path, journal)
    failure_stage = 'calculation'
    try:
        if resume_native:
            from .report_catalog import inspect
            failure_stage = 'evidence'
            summary_path, _, hyd = verified_case(previous, dest/'project.json', c)
            failure_stage = 'report'
            catalog = inspect(summary_path)
            latest = catalog['latest']
            record.update(run_id=hyd['run_id'], reused_calculation=True, report_issues=catalog['issues'])
            if latest:
                record.update(reports=latest['manifest'], reports_reused=True)
                if previous.get('report_recovery') and intact([previous['report_recovery']]):
                    record['report_recovery'] = previous['report_recovery']
            else:
                recovery = recover_case_reports(previous, dest/'project.json', c)
                record.update(report_recovery=recovery, reports=read(ROOT/recovery['path'])['reports'], reports_reused=False)
            record.update(exit_code=0, status='COMPUTED', errors=[])
        else:
            code = execute(str(dest/'project.json'), study['scenario_id'], timeout=timeout)
            state = read(dest/'state.json')
            record.update(exit_code=code, status='COMPUTED' if code == 0 else 'BLOCKED' if code == 2 else 'FAILED',
                          summary=state['latest_summary'], errors=state.get('errors', []))
    except Exception as e:
        record.update(exit_code=1, status='FAILED', error=str(e), failure_stage=failure_stage,
                      errors=[failure_stage.capitalize()+': '+str(e)])
    record['finished_utc'] = utc(); save(journal_path, journal)
    return record


def run(study_path, review_path, timeout=180):
    sp, study, rp, review = reviewed(study_path, review_path); folder = sp.parent
    if study.get('analysis_kind')=='coverage_repair':
        from .coverage_study import run as run_coverage
        return run_coverage(sp, study, rp, review, timeout)
    if study.get('coverage_policy'):
        from .spacing_cycle import run as run_cycle
        return run_cycle(sp, study, rp, review, timeout)
    return run_fixed(sp, study, rp, review, timeout)


def run_fixed(sp, study, rp, review, timeout):
    folder = sp.parent
    with lock(folder/'study.lock'):
        journal_path = folder/'execution.json'
        previous = read(journal_path) if journal_path.exists() else None
        if previous and previous['review']['sha256'] != sha(rp):
            raise ValueError('Review changed after execution; prepare a new study')
        journal = previous or dict(study=item(sp), review=item(rp), status='IN_PROGRESS', cases=[], started_utc=utc())
        journal['status'] = 'IN_PROGRESS'; save(journal_path, journal)
        for case in study['cases']:
            run_case(sp, study, rp, review, case, journal, journal_path, timeout)
        journal.update(status='COMPUTED' if all(r['status'] == 'COMPUTED' for r in journal['cases']) else 'INCOMPLETE', finished_utc=utc())
        save(journal_path, journal)
    return analyze(sp, rp)


def priorities(topics, cases, comparisons, failed):
    """No probability/risk score: rank tested response separately from missing data."""
    rows = []
    for topic in topics:
        ids = [c['id'] for c in cases if c.get('topic') == topic['id']]
        values = [r for c in comparisons if c['case'] in ids for r in c['rows']]
        missing = [x for x in ids if x in failed or not any(c['case'] == x for c in comparisons)]
        maximum = max((abs(r['delta_hw_ft']) for r in values), default=None)
        xs_max = max((r['max_matched_xs_delta_wse_ft'] for r in values), default=None)
        if not ids: priority = 'UNTESTED_NO_DEFENSIBLE_RANGE'
        elif missing: priority = 'INCOMPLETE_COMPUTATION'
        elif max(maximum, xs_max) > THRESHOLDS['sensitivity_hw_ft']: priority = 'SENSITIVE_IN_TESTED_RANGE'
        else: priority = 'SMALL_RESPONSE_IN_TESTED_RANGE'
        rows.append(dict(**topic, priority=priority, tested_case_ids=[c['case'] for c in comparisons if c['case'] in ids],
                         missing_case_ids=missing, max_abs_hw_change_ft=maximum, max_abs_matched_xs_change_ft=xs_max,
                         hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED'))
    order = {'UNTESTED_NO_DEFENSIBLE_RANGE': 0, 'INCOMPLETE_COMPUTATION': 1, 'SENSITIVE_IN_TESTED_RANGE': 2, 'SMALL_RESPONSE_IN_TESTED_RANGE': 3}
    return sorted(rows, key=lambda r: (order[r['priority']], -(r['max_abs_hw_change_ft'] or 0)))


def analyze(study_path, review_path):
    sp, study, rp, review = reviewed(study_path, review_path); folder = sp.parent
    journal = read(folder/'execution.json')
    if not intact([journal['study'], journal['review']]) or journal['review']['sha256'] != sha(rp):
        raise ValueError('Execution study/review identity mismatch')
    records = {r['id']: r for r in journal['cases']}; comparisons = []; failed = []
    for c in study['cases']:
        r = records.get(c['id'], {})
        if r.get('status') != 'COMPUTED': failed.append(c['id']); continue
        if not intact([r['summary']]): raise ValueError('Study summary changed')
        summary = read(ROOT/r['summary']['path']); hyd = summary.get('hydraulics')
        if not hyd or summary['configuration']['case_kind'] != study['case_kind']:
            raise ValueError('Study result kind or computation mismatch')
        # Bind each result to this study's own configuration and authorization.
        expected_config = read((ROOT/c['draft']['path']).parent/'project.json')
        if summary['configuration'] != expected_config: raise ValueError('Study result configuration mismatch')
        solver = ROOT/hyd['raw_hdf']['path']; manifest = read(solver.parent.parent/'manifest.json')
        if manifest['source_inputs'] != dependencies((ROOT/c['draft']['path']).parent/'project.json', expected_config):
            raise ValueError('Solver used different study case inputs')
        if not intact(manifest['source_inputs'] + manifest['input_snapshots'] + manifest['outputs']):
            raise ValueError('Study solver evidence changed')
        if c['id'] == 'baseline' or 'baseline' in failed: continue
        comparison = compare(records['baseline']['summary']['path'], r['summary']['path'], folder/'comparisons'/(c['id']+'.json'))
        comparisons.append(dict(case=c['id'], topic=c['topic'], **comparison))
    rows = priorities(study['measurement_topics'], study['cases'], comparisons, failed)
    result = dict(status='COMPARISON_REQUIRES_REVIEW' if not failed else 'INCOMPLETE', created_utc=utc(),
                  study=item(sp), review=item(rp), execution=item(folder/'execution.json'),
                  case_kind=study['case_kind'], comparisons=comparisons, measurement_priorities=rows, failed_cases=failed,
                  threshold_ft=THRESHOLDS['sensitivity_hw_ft'], engineering_acceptance='NOT_ASSESSED',
                  limitation='Ranking applies only to explicit tested ranges. Untested parameters are unresolved, not insensitive. QA and interactions remain open.')
    if study.get('analysis_kind')=='section_spacing':
        from .convergence import series
        result.update(analysis_kind='section_spacing',scope=read(ROOT/study['specification']['path'])['scope'],
                      excluded_intervals=study.get('excluded_intervals',[]), deferred_intervals=study.get('deferred_intervals',[]),
                      selection=study.get('selection'), intervals=study.get('intervals',[]),
                      cases=[dict(records.get(c['id'],{}),id=c['id'],section_count=c['section_count']) for c in study['cases']])
        from .app_revision import _diagnostic_summary
        from .spacing_coverage import observations, assess_coverage
        baseline_stations = [row['rs'] for row in read(ROOT/study['cases'][0]['geometry']['path'])['cross_sections']]
        for case in result['cases']:
            if case.get('status')!='COMPUTED':continue
            summary=read(ROOT/case['summary']['path'])
            case['diagnostics']=_diagnostic_summary(summary)
            case.update(observations(summary['hydraulics'], baseline_stations))
        result['end_coverage'] = assess_coverage(result['cases'])
        if not failed:
            convergence=series([records[c['id']]['summary']['path'] for c in study['cases']],folder/('convergence_'+unique_id()))
            result.update(status=convergence['status'],convergence=convergence)
    save(folder/'analysis.json', result)
    with (folder/'measurement_priorities.csv').open('w', newline='', encoding='utf-8-sig') as f:
        fields = ['id', 'priority', 'evidence_status', 'range_basis', 'max_abs_hw_change_ft', 'max_abs_matched_xs_change_ft', 'measurement_action']
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    text = ['# 参数敏感性与补测清单', '', '状态：'+result['status']+'；输入类别：'+study['case_kind'], '',
            '仅比较明确审核的测试范围；未测试不等于不敏感。水力 QA 待审，工程接受 NOT_ASSESSED。', '']
    for r in rows:
        text += ['## '+r['id'], '', r['priority'], '', '范围依据：'+r['range_basis'],
                 '', '最大上游参考断面水位变化（ft）：'+str(r['max_abs_hw_change_ft']), '', '补测/核查：'+r['measurement_action'], '']
    (folder/'MEASUREMENT_PRIORITIES.md').write_text('\n'.join(text), encoding='utf-8')
    return result
