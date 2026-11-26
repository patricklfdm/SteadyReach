"""Describe local evidence at the modeled flow without interpolating observational support."""
from collections import defaultdict
from .common import finite
from .app_outputs import FULL_SCOPES
from .qa import THRESHOLDS
from .lateral_coverage import SHARE_CHANGE
from .revision_inputs import station_key
from .validation_plan import score


def study_effects(studies):
    effects=defaultdict(list)
    for study in studies:
        cases={r['id']:r for r in study['cases']}
        comparisons=study.get('comparisons',[])
        if study.get('convergence'):
            comparisons=[dict(case=step['case'],previous=step['previous'],cross_section_differences=step['differences'])
                         for step in study.get('spacing_steps',[])]
        for comp in comparisons:
            case=cases[comp['case']]
            paths=[str(v['path']) for v in case.get('changes',[])]
            if study.get('convergence'):kind='spacing'
            elif any('boundar' in k for k in paths):kind='boundary'
            elif any('roughness' in k or k.endswith(('_n','manning')) for k in paths):kind='roughness'
            else:kind='alternative'
            for d in comp.get('cross_section_differences',[]):
                if kind=='spacing' and not any(float(row['downstream_rs']) <= float(d['station']) <= float(row['upstream_rs'])
                                               for row in study.get('intervals',[])):
                    continue
                if finite(d.get('delta_wse_ft')):
                    effects[d['profile'],station_key(d['station'])].append(dict(kind=kind,case=comp['case'],
                        delta_ft=d['delta_wse_ft'],previous=comp.get('previous','baseline'),
                        source_sha256=study['analysis']['sha256'],changes=case.get('changes',[])))
    return effects


def assess(summary,sections,events,diagnostics=None,studies=(),revision=None):
    hyd=summary['hydraulics'];scope=summary['configuration'].get('production_scope') or {}
    flows={(profile,station_key(row['rs'])):values.get('flow_cfs') for row in sections for profile,values in row['profiles'].items()}
    scored=score(summary,events,flows)
    # Older editions can show observed discrepancies without retroactively reserving a holdout.
    if not scope.get('validation_plan') and not scope.get('validation_protocol_active'):
        rules=scope.get('criteria') or {}
        for e in events:
            rs=(e.get('location') or {}).get('rs')
            if rs is None:continue
            delta=e.get('residual_ft');eligible=(e.get('role')=='holdout' and e.get('date') not in scope.get('calibration_dates',[])
                and e.get('kind') in ('stage','gage_height') and not e.get('issues') and finite(delta))
            limit=rules.get('max_residual_ft') if (rules.get('event')==e.get('event') and rules.get('profile',e.get('profile'))==e.get('profile')
                and (not rules.get('rs') or station_key(rules['rs'])==station_key(rs))) else None
            scored.append(dict(event=e.get('event'),date=e.get('date'),profile=e.get('profile'),rs=station_key(rs),
                role=e.get('role'),count=int(eligible),residual_ft=delta if eligible else None,uncertainty_ft=e.get('uncertainty_ft'),
                tolerance_ft=limit,state='EXCEEDED' if eligible and finite(limit) and abs(delta)>limit else 'PENDING' if eligible else 'BOUNDARY' if e.get('role')=='boundary' else 'CONTEXT'))
    effects=study_effects(studies);issues=defaultdict(list);unlocated=[]
    for item in (diagnostics or {}).get('issues',[]):
        if not item.get('profile') or item.get('station') is None:unlocated.append(item['code']);continue
        try:rs=station_key(item['station'])
        except (ValueError,TypeError):unlocated.append(item['code']);continue
        issues[item['profile'],rs].append(item['code'])
    changes={(r['profile'],station_key(r['station'])):r['change'] for r in (revision or {}).get('cross_sections',[])
             if r.get('location_status')=='SAME_CENTER'}
    shares={station_key(r['station']):r['delta_points'] for r in ((revision or {}).get('overbank_changes') or {}).get('rows',[])}
    profiles=[]
    for profile in hyd['profiles']:
        name=profile['profile_id'];points=[]
        ends={station_key(profile[k]) for k in ('headwater_rs','tailwater_rs') if profile.get(k) is not None}
        for e in scored:
            if e['profile']==name and e['rs'] in ends:e.update(state='BOUNDARY',residual_ft=None,count=0)
        for section in sections:
            rs=station_key(section['rs']);native=section['profiles'][name];q=native.get('flow_cfs')
            matches=[dict(e) for e in scored if e['profile']==name and e['rs']==rs]
            local=effects.get((name,rs),[])
            tested=sorted({r['kind'] for r in local})
            observed=[r for r in matches if r['count']]
            wet=[side for side,z in [('L',section['elevation_ft'][0]),('R',section['elevation_ft'][-1])] if native['wse_ft']>z]
            signals=sorted(set(issues.get((name,rs),[])))
            redistribute=shares.get(rs) if name.lower()=='q100' else None
            change=changes.get((name,rs))
            exceeded=any(r['state']=='EXCEEDED' for r in matches)
            if redistribute and any(finite(d) and abs(d)>=100*SHARE_CHANGE for d in redistribute):
                signals.append('REVIEW_REVISED_OVERBANK_SHARE')
            sensitive=any(abs(r['delta_ft'])>THRESHOLDS['sensitivity_hw_ft'] for r in local)
            status='INVESTIGATE' if exceeded or sensitive or wet or signals or (finite(change) and abs(change)>THRESHOLDS['sensitivity_hw_ft']) else 'PENDING'
            if (status=='PENDING' and matches and all(r['state']=='WITHIN' for r in matches) and
                all(k in tested for k in ('boundary','roughness')) and
                len({r['case'] for r in local if r['kind']=='spacing'})>=2 and not unlocated and
                (diagnostics or {}).get('warning_coverage') in FULL_SCOPES and
                finite(q) and native.get('overbank_percent') is not None):
                status='STOP_AT_TESTED_POINT'
            points.append(dict(rs=rs,flow_cfs=q,decision=status,wet_sides=wet,messages=signals,tests=local,
                               observations=matches,independent_points=len(observed),overbank_percent=native.get('overbank_percent'),
                               revision_wse_change_ft=change,overbank_change_points=redistribute))
        valid=[(s,r) for s in points for r in s['observations'] if r['count'] and finite(r['residual_ft'])]
        worst=max(valid,key=lambda v:abs(v[1]['residual_ft'])) if valid else None
        supported=[dict(rs=s['rs'],flow_cfs=s['flow_cfs']) for s in points if any(e['state']=='WITHIN' for e in s['observations'])]
        profiles.append(dict(profile=name,flow_cfs=profile['flow_cfs'],sections=points,matched_points=len(valid),
            event_count=len({(r['event'],r['date']) for _,r in valid}),supported_points=supported,
            mean_signed_ft=sum(r['residual_ft'] for _,r in valid)/len(valid) if valid else None,
            worst=dict(rs=worst[0]['rs'],event=worst[1]['event'],signed_ft=worst[1]['residual_ft']) if worst else None))
    return dict(run_id=hyd['run_id'],purpose=scope.get('purpose','screening'),profiles=profiles,unlocated_codes=unlocated,
                warning_coverage=(diagnostics or {}).get('warning_coverage'),stage_change_screen_ft=THRESHOLDS['sensitivity_hw_ft'],
                untested_flows_and_locations='PENDING')
