"""Evaluate the intended use fixed at confirmation against evidence from that edition."""
from .common import finite
from .river_observations import holdout_stages

PURPOSE = {'screening': ('conditional site screening','条件性场地初筛'),
           'comparison': ('comparison of alternatives','方案比较'),
           'review': ('submission for engineering review','提交工程复核')}


def criteria(raw):
    allowed = {'profile','dry_ends','site_geometry','min_freeboard_ft','event','max_residual_ft','rs','basis'}
    if not isinstance(raw,dict) or set(raw)-allowed:
        raise ValueError('Unknown acceptance condition / 验收条件无效')
    result = {}
    for key in ('profile','event','rs','basis'):
        val = raw.get(key,'')
        if not isinstance(val,str) or len(val)> (500 if key=='basis' else 120):
            raise ValueError('Invalid acceptance text / 验收条件文本无效')
        if val.strip():
            result[key] = val.strip()
    for key in ('min_freeboard_ft','max_residual_ft'):
        if key in raw and raw[key] is not None:
            if type(raw[key]) not in (int,float) or not finite(raw[key]) or raw[key]<0:
                raise ValueError('Supply a finite nonnegative limit in ft / 请输入非负有限英尺值')
            result[key] = raw[key]
    for key in ('dry_ends','site_geometry'):
        if key in raw and not isinstance(raw[key],bool):
            raise ValueError('Invalid evidence condition / 资料条件选项无效')
        if raw.get(key):
            result[key] = True
    if ('event' in result) != ('max_residual_ft' in result) or ('rs' in result and 'event' not in result):
        raise ValueError('Specify the observed event and its stage tolerance together / 请同时填写实测事件及水位容差')
    if any(key in result for key in ('min_freeboard_ft','max_residual_ft')) and not result.get('basis'):
        raise ValueError('Give the source for the project limit / 请说明项目阈值的依据')
    return result


def evaluate(summary, events=(), comparison=None):
    scope = summary.get('configuration',{}).get('production_scope') or {}
    purpose = scope.get('purpose','screening')
    rules = scope.get('criteria')
    rows = []
    tool='revision'
    profile=None
    def add(state,en,zh,stations=None):
        row=dict(state=state,en=en,zh=zh)
        if state!='met':
            row['action']=dict(tool=tool,profile=profile,stations=list(stations or []))
        rows.append(row)
    hyd = summary.get('hydraulics') or {}
    if rules is None:
        add('missing','Set acceptance conditions on an editable edition and confirm before running.',
            '请在可编辑版本设置用途验收条件，确认后计算。')
    else:
        rules = criteria(rules)
        profiles = [p for p in hyd.get('profiles',[]) if not rules.get('profile') or p['profile_id']==rules['profile']]
        if not profiles or not hyd.get('run_id'):
            add('missing','Supply a verified calculation for the selected profile '+str(rules.get('profile',''))+'.',
                '请补充所选工况的可追溯计算结果 '+str(rules.get('profile',''))+'。')
        for p in profiles:
            profile=p['profile_id']
            tool='revision'
            name = profile+' · '
            if not finite(p.get('flow_cfs')) or p['flow_cfs']<=0:
                add('missing',name+'Check the discharge.',name+'请核对工况流量。')
            else:
                add('met',name+f"Modeled flow {p['flow_cfs']:g} cfs.",name+f"计算流量 {p['flow_cfs']:g} cfs。")
            if rules.get('dry_ends'):
                wet = (p.get('qa') or {}).get('wet_edges')
                tool='atlas'
                if not isinstance(wet,list):
                    add('missing',name+'Obtain the cross-section end coverage check.',name+'请补各断面端点过水检查。')
                elif wet:
                    stations=', '.join(map(str,wet))
                    add('exceeded',name+'Check floodplain connectivity and extend wetted ends at RS '+stations,
                        name+'请核对漫滩连通性并延伸湿端，RS '+stations,wet)
                else:
                    add('met',name+'All section ends clear the computed water.',name+'各断面端点均高于计算水位。')
            if 'min_freeboard_ft' in rules:
                tool='native'
                value=(p.get('metrics') or {}).get('road_freeboard_ft')
                limit=rules['min_freeboard_ft']
                unit=hyd.get('unit')
                if unit=='US survey foot' and finite(value):
                    value=value*(1200/3937)/.3048
                if not finite(value) or unit not in ('ft','international ft','international foot','US survey foot'):
                    add('missing',name+f'Obtain road crest and headwater on a common datum for the {limit:g} ft limit.',
                        name+f'请补同一基准下的路顶与涵前水位，要求余高至少 {limit:g} ft。')
                else:
                    add('met' if value>=limit else 'exceeded',name+f'Road margin {value:.3f} ft; required ≥ {limit:g} ft.',
                        name+f'道路余高 {value:.3f} ft，要求 ≥ {limit:g} ft。')
        profile=None
        if purpose=='comparison':
            tool='comparison'
            comparable={p['profile'] for p in (comparison or {}).get('profiles',[]) if p.get('verified_center_count',0)>0}
            valid = (comparison or {}).get('status')=='COMPARISON_NOT_ACCEPTANCE' and bool(profiles) and all(
                p['profile_id'] in comparable for p in profiles)
            add('met' if valid else 'missing',
                'Comparable baseline and revision available.' if valid else 'Supply a computed baseline and comparable revised profiles.',
                '已有基准版及可比修订版。' if valid else '请补已计算基准版及可比的修订版工况。')
        if rules.get('site_geometry'):
            tool='field-feedback' if hyd.get('model_type')=='river' else 'invert-request'
            evidence=summary.get('configuration',{}).get('acceptance_geometry',{})
            documented=evidence.get('documented') is True
            add('met' if documented else 'missing',
                'Site geometry records supplied; verify their applicability.' if documented else
                ('Supply surveyed submerged sections with the survey manifest, originals and datum.' if hyd.get('model_type')=='river'
                 else 'Supply both invert elevations for each opening group with the original source and model datum.'),
                '已提供场地几何记录，请复核适用性。' if documented else
                ('请补水下断面测量、测量清单、原件及高程基准。' if hyd.get('model_type')=='river' else
                 '请逐组补进出口内底高程、原件及模型高程基准。'))
        tool='revision'
        if purpose=='review' and 'max_residual_ft' not in rules and not rules.get('site_geometry'):
            add('missing','Specify field geometry evidence or a held-out stage event and error limit for review.',
                '请为工程复核指定场地几何资料要求，或约定独立实测水位事件及误差。')
        if 'max_residual_ft' in rules:
            tool='observations'
            event,limit=rules['event'],rules['max_residual_ft']
            rs=rules.get('rs')
            selected=[r for r in events if r.get('event')==event and (not rs or same_rs(rs,(r.get('location') or {}).get('rs')))]
            selected=[r for r in selected if r.get('role')=='holdout' and r.get('kind') in ('stage','gage_height')]
            measured,missing,_=holdout_stages(selected)
            where=event+((' · RS '+rs) if rs else '')
            if not measured or missing or len(measured)!=len(selected):
                add('missing',where+f' · Supply comparable independent stages with uncertainty; allowed error {limit:g} ft.',
                    where+f' · 请补可比的独立实测水位及测量不确定度，允许误差 {limit:g} ft。')
            if measured:
                peak=max(abs(r['residual_ft']) for r in measured)
                add('met' if peak<=limit else 'exceeded',where+f' · Peak absolute stage error {peak:.3f} ft (limit {limit:g} ft).',
                    where+f' · 最大绝对水位误差 {peak:.3f} ft（限值 {limit:g} ft）。')
    state = ('REVISE' if any(r['state']=='exceeded' for r in rows) else
             'NEED_EVIDENCE' if any(r['state']=='missing' for r in rows) else 'CONDITIONS_MET')
    labels = {'REVISE':('Revise before intended-use delivery','修订后再按约定用途交付'),
              'NEED_EVIDENCE':('Collect evidence before intended-use delivery','补齐资料后再按约定用途交付'),
              'CONDITIONS_MET':('Purpose conditions met','已满足约定的用途条件')}
    allowed=PURPOSE[purpose]
    return dict(state=state,purpose=purpose,criteria=rules,rows=rows,
                en=labels[state][0]+' · '+allowed[0],zh=labels[state][1]+' · '+allowed[1],
                note_en='Apply the hydraulic QA limitations and verify the matching packages before release. Open items may be shared for diagnostic review.',
                note_zh='交付前须核对水力 QA 的适用限制和对应交付包。有未闭合事项时，可转交诊断资料供复核。')


def geometry_record(geometry,answers,sources):
    """Only explicit, source-linked records survive input compilation."""
    from .river_observations import datum
    if geometry.get('model_type')=='river':
        survey=geometry.get('channel_geometry_basis') in ('combined_survey_and_dem','surveyed_channel')
        records=[s for s in geometry.get('provenance',[]) if isinstance(s,dict) and s in sources
                 and s.get('role') in ('survey_manifest','survey_source')]
        documented=False
        if survey and {s['role'] for s in records}=={'survey_manifest','survey_source'}:
            from .common import ROOT,intact,read
            manifests=[s for s in records if s['role']=='survey_manifest']
            if len(manifests)==1 and intact(records):
                original=read(ROOT/manifests[0]['path'])['geometry']
                def profiles(g):
                    return [[r.get(k) for k in ('rs','station_ft','elevation_ft','cutline_xy')]
                            for r in g.get('cross_sections',[])]
                documented=(bool(original.get('cross_sections')) and profiles(geometry)==profiles(original)
                            and datum(geometry.get('vertical_datum'))==datum(original.get('vertical_datum')))
        return dict(documented=documented,records=records)
    model_datum=datum(geometry.get('vertical_datum'))
    evidence=[]
    groups=(geometry.get('structure') or {}).get('groups') or []
    for i,group in enumerate(groups):
        for field in ('us_invert_ft','ds_invert_ft'):
            answer=answers.get(f'g.structure.groups.{i}.{field}',{})
            record=answer.get('candidate_record') or {}
            source=record.get('source')
            if (answer.get('evidence_class')=='reported' and source and source in sources and
                finite(group.get(field)) and group[field]==record.get('value') and
                model_datum not in ('','UNKNOWN','UNSPECIFIED','NONE','LOCAL') and datum(record.get('datum'))==model_datum):
                evidence.append(source)
    return dict(documented=bool(groups) and len(evidence)==2*len(groups),records=evidence)


def same_rs(a,b):
    try:
        return float(a)==float(b)
    except (TypeError,ValueError):
        return str(a)==str(b)
