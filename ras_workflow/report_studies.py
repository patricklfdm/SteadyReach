"""Attach completed studies bound to this exact baseline; never rerun a solver."""
from .common import ROOT, intact, item, read, safe_path


def collect(summary_path, summary):
    from .inputs import dependencies
    from .qa import compare
    from .study import reviewed
    target = item(summary_path)
    # Search only the baseline's project, excluding studies of prior revisions.
    project = safe_path(ROOT, 'projects/' + summary['configuration']['project_id'])
    studies, sources = [], []
    for path in sorted((project / 'studies').glob('*/prepared/analysis.json')):
        analysis = read(path)
        study_entry = analysis.get('study')
        if not study_entry: continue
        plan = read(safe_path(ROOT, study_entry['path']))
        if plan.get('analysis_kind') == 'coverage_repair':
            if analysis.get('status') == 'INCOMPLETE':
                continue
            if target not in (analysis.get('baseline'), analysis.get('final_summary')):
                continue
            from .coverage_study import analyze
            actual = analyze(study_entry['path'], analysis['review']['path'], save_result=False)
            if actual != analysis:
                raise ValueError('Coverage batch assessment differs from verified computation evidence')
            studies.append(dict(analysis=item(path), coverage=analysis, cases=analysis['cases'],
                                comparisons=[], hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED'))
            sources += [item(path), study_entry, analysis['review'], analysis['execution'], plan['specification']]
            sources += plan['evidence']+plan['source_inputs']+analysis['evidence']
            continue
        if target not in plan.get('evidence', []): continue
        if analysis.get('status') not in ('COMPARISON_REQUIRES_REVIEW','STABLE_AT_REVIEW_THRESHOLD','NOT_CONVERGED') or analysis.get('failed_cases'):
            continue
        entries = [study_entry, analysis['review'], analysis['execution']]
        if not intact(entries): raise ValueError('Bound sensitivity study evidence changed')
        _, plan, _, _ = reviewed(study_entry['path'], analysis['review']['path'])
        journal = read(ROOT / analysis['execution']['path'])
        if journal['study'] != study_entry or journal['review'] != analysis['review']:
            raise ValueError('Sensitivity execution identity mismatch')
        records = {v['id']: v for v in journal['cases']}
        cases = []
        for case in plan['cases']:
            record = records[case['id']]
            if record['status'] != 'COMPUTED' or not intact([record['summary']]):
                raise ValueError('Sensitivity case is not an intact computation')
            result = read(ROOT / record['summary']['path']); h = result['hydraulics']
            config_path = (ROOT / case['draft']['path']).parent / 'project.json'
            config = read(config_path)
            if result['configuration'] != config: raise ValueError('Sensitivity configuration mismatch')
            manifest_path = (ROOT / h['raw_hdf']['path']).parent.parent / 'manifest.json'
            manifest = read(manifest_path)
            if manifest['source_inputs'] != dependencies(config_path, config):
                raise ValueError('Sensitivity source inputs changed')
            bound = manifest['source_inputs'] + manifest['input_snapshots'] + manifest['outputs']
            if not intact(bound): raise ValueError('Sensitivity native evidence changed')
            entries += [record['summary'], item(manifest_path), case['draft'], case['geometry']] + bound
            cases.append(dict(id=case['id'], changes=case['changes'], run_id=h['run_id'],
                              boundaries=h.get('boundaries'), boundary_slopes=h.get('boundary_slopes')))
            if plan.get('analysis_kind')=='section_spacing':
                from .app_revision import _diagnostic_summary
                from .spacing_coverage import observations
                baseline_stations = [row['rs'] for row in read(ROOT/plan['cases'][0]['geometry']['path'])['cross_sections']]
                cases[-1].update(status='COMPUTED', section_count=case['section_count'], diagnostics=_diagnostic_summary(result),
                                 **observations(h, baseline_stations))
        baseline = records['baseline']['summary']['path']
        repeat = compare(summary_path, baseline, None)
        if (repeat['unmatched_baseline_profiles'] or repeat['unmatched_candidate_profiles']
            or any(v['removed_stations'] or v['added_stations'] for v in repeat['rows'])
            or any(r['delta_wse_ft'] != 0 for r in repeat['cross_section_differences'])):
            raise ValueError('Sensitivity baseline does not reproduce the report baseline')
        comparisons = []
        for case in plan['cases']:
            if case['id'] == 'baseline': continue
            actual = compare(baseline, records[case['id']]['summary']['path'], None)
            actual = dict(case=case['id'], topic=case['topic'], **actual)
            saved = [v for v in analysis['comparisons'] if v['case'] == case['id']]
            if saved != [actual]: raise ValueError('Sensitivity comparison differs from native outputs')
            comparisons.append(actual)
        convergence=None
        end_coverage=None
        if plan.get('analysis_kind')=='section_spacing':
            from .spacing_coverage import assess_coverage
            end_coverage=assess_coverage(cases)
            if 'end_coverage' in analysis and analysis['end_coverage'] != end_coverage:
                raise ValueError('Spacing end-coverage assessment differs from native outputs')
            from .convergence import assess
            from .qa import THRESHOLDS
            convergence=analysis.get('convergence')
            if not convergence or not intact(convergence['sources']+convergence['comparisons']):
                raise ValueError('Spacing convergence evidence changed')
            pairs=[]
            for i in range(len(plan['cases'])-1):
                a,b=plan['cases'][i:i+2]
                pair=compare(records[a['id']]['summary']['path'],records[b['id']]['summary']['path'],None)
                if pair!=read(ROOT/convergence['comparisons'][i]['path']):raise ValueError('Spacing comparison differs from native outputs')
                pairs.append(pair)
            rows=assess(pairs,THRESHOLDS['sensitivity_hw_ft'])
            expected_status='STABLE_AT_REVIEW_THRESHOLD' if all(r['status']=='STABLE_AT_REVIEW_THRESHOLD' for r in rows) else 'NOT_CONVERGED'
            if rows!=convergence['rows'] or convergence['threshold_ft']!=THRESHOLDS['sensitivity_hw_ft'] or analysis['status']!=expected_status or convergence['status']!=expected_status:
                raise ValueError('Spacing convergence assessment changed')
            entries+=convergence['sources']+convergence['comparisons']
        studies.append(dict(analysis=item(path), cases=cases, comparisons=comparisons,convergence=convergence,
                            end_coverage=end_coverage, excluded_intervals=plan.get('excluded_intervals',[]), deferred_intervals=plan.get('deferred_intervals',[]),
                            selection=plan.get('selection'), intervals=plan.get('intervals',[]),
                            hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED'))
        sources += [item(path)] + entries + plan['evidence'] + [plan['specification']] + plan['source_inputs']
    unique = {v['path']: v for v in sources}
    return studies, list(unique.values())
