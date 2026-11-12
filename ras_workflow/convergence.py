"""Nested section convergence checks at headwater AND retained sections.

Two consecutive refinements must meet the existing review threshold. Passing
this numerical check does not clear warning review or establish design safety.
"""
import re
from .common import ROOT,read,item,intact,safe_path,save,utc
from .qa import compare,THRESHOLDS
from .qa_review import load_summary


def assess(comparisons,threshold):
    if len(comparisons)<2:raise ValueError('At least three runs / two refinements required')
    if any(c['unmatched_baseline_profiles'] or c['unmatched_candidate_profiles'] for c in comparisons):
        raise ValueError('All convergence profiles must match')
    names=[r['profile'] for r in comparisons[0]['rows']]
    if any([r['profile'] for r in c['rows']]!=names for c in comparisons):raise ValueError('Profile order changed')
    rows=[]
    for i,name in enumerate(names):
        last=[c['rows'][i] for c in comparisons[-2:]]
        retained=all(not r['removed_stations'] for r in last)
        hw=retained and all(abs(r['delta_hw_ft'])<=threshold for r in last)
        xs=retained and all(r['max_matched_xs_delta_wse_ft']<=threshold for r in last)
        rows.append(dict(profile=name,headwater_stable=hw,retained_sections_stable=xs,
                         status='STABLE_AT_REVIEW_THRESHOLD' if hw and xs else 'NOT_CONVERGED',
                         last_two_hw_deltas_ft=[r['delta_hw_ft'] for r in last],
                         last_two_max_xs_deltas_ft=[r['max_matched_xs_delta_wse_ft'] for r in last]))
    return rows


def series(summaries,output):
    if len(summaries)<3:raise ValueError('Supply at least three ordered nested refinements')
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve previous convergence evidence; use a new directory')
    loaded=[load_summary(p) for p in summaries]
    if len({h['run_id'] for _,_,h in loaded})!=len(loaded):raise ValueError('Distinct real solver runs required')
    sources=[];last_expected=None;last_flow=None;last_structure=None;last_plan=None
    for path,summary,hyd in loaded:
        solver=(ROOT/hyd['raw_hdf']['path']).parent.parent
        manifest=read(solver/'manifest.json');request=read(solver/'request.json')
        if not intact(manifest['native_before']+manifest['outputs']):raise ValueError('Native run evidence changed')
        expected=request['expected'];xs=expected.get('cross_sections')
        if not xs:raise ValueError('Explicit external section geometry required for a spacing series')
        flow=next(v['sha256'] for v in manifest['native_before'] if v['path'].lower().endswith('.f01'))
        geometry=next(ROOT/v['path'] for v in manifest['native_before'] if v['path'].lower().endswith('.g01'))
        plan=next(ROOT/v['path'] for v in manifest['native_before'] if v['path'].lower().endswith('.p01'))
        structure,settings=nonspacing_signature(geometry.read_text(encoding='ascii'),plan.read_text(encoding='ascii'))
        if last_expected:
            for key in ['groups','channel_n','overbank_n','culvert_n','road_width_ft','road_min_ft','us_xs_rs','ds_xs_rs','structure_rs']:
                if expected[key]!=last_expected[key]:raise ValueError('Non-spacing input changed: '+key)
            if flow!=last_flow:raise ValueError('Boundary/flow inputs changed')
            if structure!=last_structure:raise ValueError('Full native structure/deck input changed')
            if settings!=last_plan:raise ValueError('Non-diagnostic solver plan settings changed')
            old={r['rs']:r for r in last_expected['cross_sections']};new={r['rs']:r for r in xs}
            if not old.keys()<=new.keys() or len(new)<=len(old):raise ValueError('Series must add sections and retain every original')
            for rs,a in old.items():
                for key in ['station_ft','elevation_ft','bank_stations_ft','center_xy','cutline_xy','expansion_contraction']:
                    if a[key]!=new[rs][key]:raise ValueError('Original section changed: '+str(rs)+' / '+key)
        last_expected=expected;last_flow=flow;last_structure=structure;last_plan=settings
        sources += [item(path),item(solver/'manifest.json'),item(solver/'request.json')]
    out.mkdir(parents=True);comparisons=[]
    for i in range(len(loaded)-1):
        comparisons.append(compare(loaded[i][0],loaded[i+1][0],out/f'pair_{i+1}.json'))
    rows=assess(comparisons,THRESHOLDS['sensitivity_hw_ft'])
    result=dict(status='STABLE_AT_REVIEW_THRESHOLD' if all(r['status']=='STABLE_AT_REVIEW_THRESHOLD' for r in rows) else 'NOT_CONVERGED',
                created_utc=utc(),sources=sources,threshold_ft=THRESHOLDS['sensitivity_hw_ft'],rows=rows,
                comparisons=[item(out/f'pair_{i+1}.json') for i in range(len(comparisons))],
                hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED',
                limitation='Native warnings, input sufficiency, terrain resolution and physical applicability remain separate.')
    save(out/'convergence.json',result);return result


def nonspacing_signature(geometry,plan):
    blocks=re.split(r'(?m)^Type RM Length L Ch R =',geometry)[1:]
    structures=[b for b in blocks if b.lstrip().startswith('2 ,')]
    if len(structures)!=1:raise ValueError('Spacing series requires one inspected culvert record')
    settings=re.sub(r'(?m)^(?:Plan Title|Short Identifier|Global Log Level|Log Output Level)=.*\n?','',plan)
    return structures[0],settings
