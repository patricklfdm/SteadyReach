"""Nested section convergence checks at headwater AND retained sections.

Two consecutive refinements must meet the existing review threshold. Passing
this numerical check does not clear warning review or establish design safety.
"""
import math
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
    sources=validate_native_series(loaded)
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


def validate_native_series(loaded):
    """Read-only validation reusable by resumable coverage/spacing batches."""
    if len(loaded)<3 or len({h['run_id'] for _,_,h in loaded})!=len(loaded):
        raise ValueError('At least three distinct actual nested computations required')
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
        structure,settings=nonspacing_signature(geometry.read_text(encoding='ascii'),plan.read_text(encoding='ascii'), expected.get('model_type','culvert'))
        if last_expected:
            validate_nested(last_expected,expected)
            if flow!=last_flow:raise ValueError('Boundary/flow inputs changed')
            if structure!=last_structure:raise ValueError('Full native structure/deck input changed')
            if settings!=last_plan:raise ValueError('Non-diagnostic solver plan settings changed')
        last_expected=expected;last_flow=flow;last_structure=structure;last_plan=settings
        sources += [item(path),item(solver/'manifest.json'),item(solver/'request.json')]
    return sources


def validate_nested(previous,current):
    """Keep hydraulic controls fixed and conserve the three interval lengths."""
    changing={'cross_sections','xs_count','xs_stations','manning_by_section','ineffective_by_section'}
    for key in previous.keys()|current.keys():
        if key not in changing and previous.get(key)!=current.get(key):
            raise ValueError('Non-spacing input changed: '+key)
    old=previous['cross_sections'];new=current['cross_sections']
    old_ids=[r['rs'] for r in old];new_ids=[r['rs'] for r in new]
    if len(set(new_ids))!=len(new_ids) or not set(old_ids)<=set(new_ids) or len(new)<=len(old):
        raise ValueError('Series must add sections and retain every original')
    indices=[new_ids.index(rs) for rs in old_ids]
    if indices!=sorted(indices) or indices[0]!=0 or indices[-1]!=len(new)-1:
        raise ValueError('Spacing trials must preserve endpoints and section order')
    for i,a in enumerate(old):
        b=new[indices[i]]
        for key in ('station_ft','elevation_ft','bank_stations_ft','center_xy','cutline_xy',
                    'expansion_contraction','manning_segments','ineffective_left','ineffective_right'):
            if a.get(key)!=b.get(key):
                raise ValueError('Original section changed: '+str(a['rs'])+' / '+key)
        for key in ('manning_by_section','ineffective_by_section'):
            if previous.get(key) is not None and (current.get(key) is None or previous[key][i]!=current[key][indices[i]]):
                raise ValueError('Original section control changed: '+str(a['rs'])+' / '+key)
        parts=new[indices[i]:indices[i+1]] if i+1<len(old) else [b]
        for axis in range(3):
            total=sum(r['reach_lengths_ft'][axis] for r in parts)
            if not math.isclose(total,a['reach_lengths_ft'][axis],rel_tol=1e-9,abs_tol=1e-6):
                raise ValueError('Reach length total changed: '+str(a['rs']))


def nonspacing_signature(geometry,plan,model_type='culvert'):
    blocks=re.split(r'(?m)^Type RM Length L Ch R =',geometry)[1:]
    structures=[b for b in blocks if not re.match(r'\s*1\s*,',b)]
    if model_type=='river' and structures:raise ValueError('River spacing series contains a structure')
    if model_type!='river' and (len(structures)!=1 or not re.match(r'\s*2\s*,',structures[0])):
        raise ValueError('Spacing series requires one inspected culvert record')
    settings=re.sub(r'(?m)^(?:Plan Title|Short Identifier|Global Log Level|Log Output Level)=.*\n?','',plan)
    return structures,settings
