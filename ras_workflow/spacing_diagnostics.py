"""Locate numerical spacing response in authenticated native case results."""
import copy
from .common import ROOT, finite, intact, read


def identity(row):
    return row['profile'], row['river'], row['reach'], float(row['rs'])


def assemble(case_ids, series, threshold):
    """Compare only identical section/profile identities in consecutive levels."""
    if len(series)!=3 or len(case_ids)!=3 or len(set(case_ids))!=3:
        raise ValueError('Three distinct ordered spacing cases required')
    if not finite(threshold) or threshold<=0:
        raise ValueError('A positive spacing review threshold is required')
    maps=[]
    for rows in series:
        indexed={identity(row):row for row in rows}
        if len(indexed)!=len(rows):raise ValueError('Repeated native section/profile identity')
        maps.append(indexed)
    if not maps[0] or not set(maps[0])<=set(maps[1])<=set(maps[2]):
        raise ValueError('Native spacing section/profile identities are not nested')
    profiles={key[:3] for key in maps[0]}
    if any({key[:3] for key in index}!=profiles for index in maps):
        raise ValueError('Spacing profiles or reaches differ')
    rows=[];pairs=[]
    metrics=('wse_ft','egl_ft','critical_wse_ft','velocity_fts','froude','min_error_ft','left_excess_ft','right_excess_ft')
    for key, finest in maps[-1].items():
        values=[]
        for cid,index in zip(case_ids,maps):
            native=index.get(key)
            values.append(None if native is None else dict(case=cid,**{k:native.get(k) for k in metrics},
                issues=native.get('issues',[]),wet_intervals_ft=native.get('wet_intervals_ft')))
        deltas=[];missing=[]
        for a,b in zip(values,values[1:]):
            comparable=a is not None and b is not None
            valid=comparable and finite(a['wse_ft']) and finite(b['wse_ft'])
            deltas.append(b['wse_ft']-a['wse_ft'] if valid else None)
            missing.append(comparable and not valid)
        largest=max((abs(v) for v in deltas if v is not None),default=None)
        exceed=[i+1 for i,value in enumerate(deltas) if value is not None and abs(value)>threshold]
        wet=[v['case'] for v in values if v and any(finite(v[k]) and v[k]>0 for k in ('left_excess_ft','right_excess_ft'))]
        flags=[]
        if exceed:flags.append('WSE_CHANGE_ABOVE_THRESHOLD')
        if any(missing):flags.append('COMPARISON_RESULT_MISSING')
        if wet:flags.append('WET_SECTION_END')
        if any(v and v['issues'] for v in values):flags.append('NATIVE_OR_NUMERICAL_DIAGNOSTIC')
        transitions=[]
        for i,(a,b) in enumerate(zip(values,values[1:])):
            if a and b and finite(a['froude']) and finite(b['froude']) and (a['froude']<1)!=(b['froude']<1):
                transitions.append(i+1)
        if transitions:flags.append('CHANNEL_FROUDE_CROSSES_ONE')
        rows.append(dict(profile=key[0],river=key[1],reach=key[2],rs=finest['rs'],
            origin='BASELINE' if key in maps[0] else 'FIRST_REFINEMENT' if key in maps[1] else 'SECOND_REFINEMENT',
            cases=values,delta_wse_ft=deltas,maximum_abs_delta_ft=largest,exceeding_pairs=exceed,
            missing_result_pairs=[i+1 for i,v in enumerate(missing) if v],wet_cases=wet,
            channel_froude_crossings=transitions,flags=flags,section=finest))
    for profile,river,reach in sorted(profiles):
        subset=[r for r in rows if (r['profile'],r['river'],r['reach'])==(profile,river,reach)]
        for i in range(2):
            matched=[r for r in subset if r['cases'][i] is not None and r['cases'][i+1] is not None]
            valid=[r for r in matched if r['delta_wse_ft'][i] is not None]
            maximum=max((abs(r['delta_wse_ft'][i]) for r in valid),default=None)
            pairs.append(dict(profile=profile,river=river,reach=reach,pair=i+1,from_case=case_ids[i],to_case=case_ids[i+1],
                matched_sections=len(matched),compared_sections=len(valid),missing_results=len(matched)-len(valid),
                above_threshold=sum(abs(r['delta_wse_ft'][i])>threshold for r in valid),max_abs_delta_ft=maximum,
                worst_stations=[r['rs'] for r in valid if abs(r['delta_wse_ft'][i])==maximum]))
    # Ranking is an observation ordering, not a model-quality or safety score.
    rows.sort(key=lambda r:(not bool(r['missing_result_pairs']),not bool(r['exceeding_pairs']),
                           -(r['maximum_abs_delta_ft'] or 0),not bool(r['wet_cases']),r['profile'],-float(r['rs'])))
    return dict(rows=rows,pairs=pairs,threshold_ft=threshold,section_profiles=len(rows),
        above_threshold=sum(bool(r['exceeding_pairs']) for r in rows),missing_results=sum(bool(r['missing_result_pairs']) for r in rows),
        wet_section_profiles=sum(bool(r['wet_cases']) for r in rows),attention=sum(bool(r['flags']) for r in rows),
        warnings_resolved=0,geometry_changed=False,solver_started=False,engineering_acceptance='NOT_ASSESSED')


def restore_legacy_coverage(analysis):
    """Derive absent pre-cycle display fields in memory; preserve sealed files."""
    if 'end_coverage' in analysis or analysis.get('coverage_batch'):
        return analysis
    from .study import reviewed
    from .spacing_coverage import observations, assess_coverage
    _,plan,_,_=reviewed(analysis['study']['path'],analysis['review']['path'])
    baseline=[row['rs'] for row in read(ROOT/plan['cases'][0]['geometry']['path'])['cross_sections']]
    restored=copy.deepcopy(analysis)
    for case in restored['cases']:
        if case.get('status')!='COMPUTED':continue
        if not intact([case['summary']]):raise ValueError('Legacy spacing summary changed')
        actual=observations(read(ROOT/case['summary']['path'])['hydraulics'],baseline)
        if {float(v) for v in case.get('wet_sections',[])}!={float(v) for v in actual['wet_sections']}:
            raise ValueError('Legacy spacing wet sections differ from native results')
        for field,value in actual.items():
            if field!='wet_sections' and field in case and case[field]!=value:
                raise ValueError('Legacy spacing coverage metadata changed')
            case[field]=value
    restored['end_coverage']=assess_coverage(restored['cases'])
    return restored


def collect(key, body):
    from . import app_core as core
    from .spacing_cycle import round_evidence, verify
    from .result_atlas import native_rows, assemble as panels
    m=core.model(key);core.require_idle(m)
    entry=m.get('latest_spacing')
    if (not entry or body.get('study_token')!=entry['sha256'] or not intact([entry])
            or body.get('summary_hash')!=m.get('summary',{}).get('sha256') or not intact([m['summary']])):
        raise ValueError('Spacing result or baseline changed; reopen results')
    analysis=read(ROOT/entry['path'])
    if analysis.get('failed_cases') or analysis.get('status')=='INCOMPLETE':
        raise ValueError('Complete the spacing batch before comparing all three levels')
    sources=[entry,m['summary']]
    if analysis.get('coverage_batch'):sources+=verify(analysis)
    analysis=restore_legacy_coverage(analysis)
    verified=round_evidence(analysis)
    if m['summary'] not in verified['plan']['evidence']:
        raise ValueError('Spacing study belongs to another baseline')
    sources+=verified['entries']
    series=[];cases=[];unlocated=[]
    for case,loaded,geometry in zip(analysis['cases'],verified['loaded'],verified['geometries']):
        path,summary,hyd=loaded
        diagnostic=hyd.get('diagnostics')
        if hyd.get('unit')!='international ft' or not diagnostic or not intact([diagnostic]):
            raise ValueError('Spacing native units or diagnostic evidence unavailable')
        data=read(ROOT/diagnostic['path']);sources.append(diagnostic)
        if data['run_id']!=hyd['run_id'] or not intact(data['sources']):
            raise ValueError('Spacing diagnostic identity or evidence changed')
        if summary.get('native_supplement'):
            from .app_outputs import validate,diagnostics
            supplement=validate(summary['native_supplement'])
            data=diagnostics(hyd,supplement);sources.append(summary['native_supplement'])
        sources+=data['sources']
        actual=panels(native_rows(hyd),data,geometry)
        series.append(actual['sections'])
        cases.append(dict(id=case['id'],run_id=hyd['run_id'],summary=case['summary'],section_count=case['section_count'],
                          warning_coverage=actual['warning_coverage']))
        unlocated += [dict(case=case['id'],issue=issue) for issue in actual['unlocated_issues']]
    result=assemble([c['id'] for c in cases],series,analysis['convergence']['threshold_ft'])
    for row in analysis['convergence']['rows']:
        observed=[v['max_abs_delta_ft'] for v in result['pairs'] if v['profile']==row['profile']]
        if observed!=row['last_two_max_xs_deltas_ft']:
            raise ValueError('Located spacing response differs from verified convergence')
    result.update(status='SPACING_OBSERVATIONS_NOT_ACCEPTANCE',cases=cases,study=entry,summary=m['summary'],
        convergence_status=analysis['status'],coverage_status=analysis['end_coverage']['status'],
        cycle_stop=(analysis.get('coverage_batch') or {}).get('status'),unlocated_issues=unlocated,
        horizontal_crs=verified['geometries'][-1]['horizontal_crs'],
        sources=list({e['path']:e for e in sources}.values()))
    if not intact(result['sources']):raise ValueError('Spacing evidence changed during review')
    return result
