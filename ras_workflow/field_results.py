"""Native results for field follow-up editions, shared by UI, reports and packages."""
from .common import ROOT,intact,read
from .qa import verified_profiles,THRESHOLDS
from .revision_inputs import station_key


def collect(summary):
    ref=summary['configuration'].get('field_feedback')
    if not ref:return None,[]
    if not intact([ref]):raise ValueError('Field feedback record changed')
    spec=read(ROOT/ref['path'])
    if spec['child']!=summary['configuration']['project_id'] or not intact(spec['sources']):
        raise ValueError('Field feedback is incomplete or belongs to another edition')
    data={k:spec[k] for k in ('mode','assumed','area','parent_summary','geometry_summary','engineering_acceptance')}
    data.update(source=ref,run_id=summary['hydraulics']['run_id'])
    water={name:{station_key(rs):z for rs,z in values.items()} for name,values in verified_profiles(summary['hydraulics']).items()}
    if data['mode']=='event':
        expected=[r['profile'] for r in spec['stages']]
        if list(water)!=expected or any(abs(p['flow_cfs']-spec['flow_cfs'])>1.e-5 for p in summary['hydraulics']['profiles']):
            raise ValueError('Native event profiles or discharge differ from the reviewed controls')
        data.update({k:spec[k] for k in ('event','date','stages','uses','flow_cfs')})
        base=water['EventBase'];data['responses']=[];data['observations']=[]
        for row in spec['rows']:
            rs=row['rs']
            data['observations'].append(dict(row,residual_ft=base[rs]-row['stage_ft'] if row['role']!='boundary' else None))
        tail=next(r['rs'] for r in spec['rows'] if r['role']=='boundary')
        for control in spec['stages']:
            profile=control['profile']
            if abs(water[profile][tail]-control['stage_ft'])>.01:raise ValueError('Native tailwater differs from the confirmed input')
            if profile=='EventBase':continue
            differences={rs:z-base[rs] for rs,z in water[profile].items()}
            selected={rs:differences[rs] for rs in spec['area']}
            peak=max(selected,key=lambda rs:abs(selected[rs]))
            data['responses'].append(dict(profile=profile,peak_rs=peak,delta_ft=selected[peak],by_rs=differences,
                affected=[rs for rs,v in selected.items() if abs(v)>THRESHOLDS['sensitivity_hw_ft']],
                threshold_ft=THRESHOLDS['sensitivity_hw_ft']))
    else:
        data.update({k:spec[k] for k in ('comparison','decision','selected','condition')})
        refwater=verified_profiles(read(ROOT/spec['geometry_summary']['path'])['hydraulics'])
        normalized={name:{station_key(rs):v for rs,v in w.items()} for name,w in refwater.items()}
        if water.keys()!=normalized.keys() or any(set(w)!=set(normalized[n]) for n,w in water.items()):
            raise ValueError('Native section inventory differs from the selected geometry run')
        data['repeat_max_delta_ft']=max(abs(z-normalized[n][rs]) for n,w in water.items() for rs,z in w.items())
    return data,[ref,*spec['sources']]


def verified_observations(data):
    """Only point-identified field records can support an independent residual or measured interval."""
    rows=[]
    # The complete event must remain independent of any assumed boundary.
    if data['assumed']:return rows
    for r in data['observations']:
        if r['point_type']!='measured' or r['basis']!='documented' or not r['uncertainty_ft']:continue
        rows.append(dict(role=r['role'],kind='boundary_stage' if r['role']=='boundary' else 'stage',
                         location={'rs':r['rs']},event=r['event'],date=r['date'],event_eligible=True,issues=[],
                         model_datum=r['datum'],source=r['original_source']+' | '+r['reference'],flow_cfs=r['flow_cfs'],
                         observed_ft=r['stage_ft'],residual_ft=r['residual_ft'],uncertainty_ft=r['uncertainty_ft']))
    return rows


def lines(data,cn):
    tr=lambda a,b:b if cn else a
    result=[tr('Field follow-up','现场反馈复核')+' · '+data['run_id'],
            (tr('ASSUMED FEEDBACK. Scenario for workflow testing. Field accuracy and sign-off remain open.',
                '假设反馈。此情景用于验证工作流，现场精度和工程签审仍待核实。') if data['assumed'] else
             tr('Field records and engineering choices apply to the named event or geometry only.','现场资料与工程决定限于所列事件或几何。'))]
    if data['mode']=='event':
        rows=data['observations'];b=next(r for r in rows if r['role']=='boundary')
        result.append(f"{data['date']} · {data['event']} · {data['flow_cfs']:.2f} cfs · RS {b['rs']} · {b['datum']}")
        result.append(tr('Downstream stages','下游尾水')+' (ft) · '+', '.join(f"{r['profile']} {r['stage_ft']:.3f}" for r in data['stages']))
        result.append(tr('Boundary uncertainty and basis','边界不确定度和依据')+f" · ±{b['uncertainty_ft']:.3f} ft · {b['reference']}")
        for r in data['responses']:
            result.append(f"{r['profile']} · RS {r['peak_rs']} · Δ {r['delta_ft']:+.3f} ft · {len(r['affected'])}/{len(data['area'])} "+
                          tr('sections above','个断面超过')+f" {r['threshold_ft']:.2f} ft")
            station_list=', '.join(r['affected']) or '—'
            result.append(tr('Affected RS in review area','关注河段内受影响的 RS')+' · '+station_list)
        result.append(tr('Documented / assumed / unresolved point records','有记录／假设／待补的点记录数')+' · '+
                      ' / '.join(str(len(data['uses'][s])) for s in ('documented','assumed','unresolved')))
    else:
        d=data['comparison'];result.append(f"RS {d['station']} · {d['profile']} · {data['decision']} · {data['selected']}")
        result.append(data['condition'])
        base={r['rs']:r['wse_ft'] for r in d['variants']['baseline']['sections']}
        for k,v in d['variants'].items():
            result.append(k+' · '+', '.join(f"RS {r['rs']} {r['wse_ft']:.3f} ft (Δ {r['wse_ft']-base[r['rs']]:+.3f})" for r in v['sections']))
            for row in v['sections']:
                sides=' / '.join('—' if x is None else f'{x:.2f}%' for x in row['share'])
                result.append(f"RS {row['rs']} · "+tr('left / right overbank','左／右漫滩')+' · '+sides)
        roads=sorted({c['name'] or c['layer'] for v in d['variants'].values() for s in v['strips'] for c in s['crossings']})
        if roads:result.append(tr('Mapped road or levee lines in tested strips','检查条带中的道路线或堤线')+' · '+', '.join(roads))
        result.append(tr('Repeat run maximum absolute WSE difference','重算与选定版本的最大绝对水位差')+f" · {data['repeat_max_delta_ft']:.4f} ft")
    return result
