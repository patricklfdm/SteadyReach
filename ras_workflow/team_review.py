"""Formal local submissions and offline station comments for a family of editions."""
from .interface_style import embedded_interface_style
from . import app_core as core
from .common import ROOT, digest, intact, lock, read, save, utc
from .revision_inputs import bound_inputs, hydraulic_inputs, station_key

SCHEMA = 'steadyreach_team_review_1'
STATES = {'submit': 'SUBMITTED', 'return': 'RETURNED', 'review': 'REVIEWED',
          'withdraw': 'WITHDRAWN', 'supersede': 'SUPERSEDED', 'deliver': 'DELIVERED'}
ROLES = {'submit': 'modeler', 'return': 'reviewer', 'review': 'reviewer', 'withdraw': 'lead',
         'supersede': 'modeler', 'deliver': 'lead'}


def family(model):
    """Walk only registered parent IDs; include archived parents in the family history."""
    from .edition_storage import archived
    offline = {r['id']: r for r in archived(ROOT)}
    ids = []
    while model:
        key = model['id']
        if key in ids:
            raise ValueError('Project ancestry contains a cycle / 项目版本存在循环引用')
        ids.append(key)
        parent = (model.get('parent_revision') or {}).get('project_id')
        if not parent:
            break
        model = offline.get(parent) or core.model(parent)
    return ids


def context(model):
    reference = model.get('summary')
    if not reference or not intact([reference]):
        raise ValueError('Restore the calculated edition first / 请先恢复已计算的版本')
    summary = read(ROOT/reference['path'])
    native = summary['hydraulics']
    if not intact([native['raw_hdf']]):
        raise ValueError('The native result changed / 原生结果文件已改变')
    edition = dict(project=model['id'], run=native['run_id'], summary_sha256=reference['sha256'],
                   hdf_sha256=native['raw_hdf']['sha256'])
    inputs = {}
    if model.get('native_review'):
        from .qa import verified_profiles
        stations = {station_key(rs) for profile in verified_profiles(native).values() for rs in profile}
        inputs['native_inputs_and_output'] = edition['hdf_sha256']
    else:
        config, geometry, _ = bound_inputs(summary)
        controls = hydraulic_inputs(config, geometry, native['scenario_id'])
        inputs.update({'control/'+k: digest(v) for k,v in controls.items()})
        for row in geometry['cross_sections']:
            inputs['RS/'+station_key(row['rs'])] = digest(row)
        stations = {station_key(row['rs']) for row in geometry['cross_sections']}
        inputs['observations'] = digest([r['sha256'] for field in ('returned_observations','returned_observation_originals')
                                         for r in config.get(field,[])])
    return edition, inputs, sorted(stations,key=float,reverse=True)


def read_history(path):
    if not path.exists():
        return []
    rows = read(path)
    if not isinstance(rows,list):
        raise ValueError('Invalid formal review history / 正式复核历史格式有误')
    previous = None
    for number,row in enumerate(rows,1):
        if not isinstance(row,dict):
            raise ValueError('Invalid formal review entry / 复核记录格式有误')
        payload = {k:v for k,v in row.items() if k!='token'}
        if row.get('sequence')!=number or 'previous' not in row or row['previous']!=previous or digest(payload)!=row.get('token'):
            raise ValueError('Formal review history changed / 正式复核历史已改变')
        previous = row['token']
    return rows


def head(rows):
    return rows[-1]['token'] if rows else None


def decisions(rows, lineage, inputs):
    """Carry a station comment iff the selected dependency fingerprints still match."""
    result = []
    for row in rows:
        if row['action'] not in ('return','review') or row['edition']['project'] not in lineage:
            continue
        changed = [key for key,v in row['dependencies'].items() if inputs.get(key)!=v]
        result.append(dict(token=row['token'],station=row['station'],note=row['note'],action=row['action'],
                           changed=changed,state='RECHECK' if changed else 'CARRIED'))
    return result


def inspect(key):
    model = core.model(key)
    edition,inputs,stations = context(model)
    lineage = family(model)
    rows = read_history(ROOT/'status/team_review'/lineage[-1]/'history.json')
    current = [r for r in rows if r['edition']==edition]
    return dict(schema=SCHEMA,edition=edition,head=head(rows),state=current[-1]['state'] if current else 'DRAFT',
                stations=stations,dependencies=sorted(inputs),history=rows,decisions=decisions(rows,lineage,inputs))


def offline_form(key, expected_head):
    import json
    from pathlib import Path
    current=inspect(key)
    if current['head']!=expected_head or current['state']!='SUBMITTED':
        raise ValueError('Refresh the submitted edition / 请刷新已提交的版本')
    request={k:current[k] for k in ('schema','edition','head','stations','dependencies')}
    encoded=json.dumps(request,ensure_ascii=False).replace('<',r'\u003c')
    template=Path(__file__).parent/'templates/team_form.html'
    return dict(html=template.read_text(encoding='utf-8').replace('__INTERFACE_STYLE__',embedded_interface_style()).replace('__REVIEW_REQUEST__',encoded))


def text_field(value, limit, name):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError('Supply / 请填写 '+name)
    return value.strip()


def append(rows, edition, action, actor, **fields):
    row = dict(sequence=len(rows)+1,previous=head(rows),edition=edition,action=action,state=STATES[action],
               role=ROLES[action],actor=actor,at=utc(),**fields)
    row['token'] = digest(row)
    rows.append(row)
    return row


def decide(key, body):
    """An offline comment uses the same checks and transition as an in-page decision."""
    action = body.get('action')
    if action not in ('submit','return','review','withdraw','deliver'):
        raise ValueError('Unknown formal review action')
    actor = text_field(body.get('actor'),100,'operator / 经办人')
    note = text_field(body.get('note'),1500,'review note / 意见')
    model = core.model(key)
    core.require_idle(model)
    lineage = family(model)
    path = ROOT/'status/team_review'/lineage[-1]/'history.json'
    with lock(path.with_suffix('.lock')):
        model=core.model(key)
        edition,inputs,stations = context(model)
        if body.get('schema')!=SCHEMA or body.get('edition')!=edition:
            raise ValueError('Different edition or run. Reopen the matching project. / 版本或运行不匹配，请打开对应项目')
        rows = read_history(path)
        if 'head' not in body or body['head']!=head(rows):
            raise ValueError('Review changed. Refresh and recheck the comment. / 复核历史已有更新，请刷新核对')
        current = [r for r in rows if r['edition']==edition]
        state = current[-1]['state'] if current else 'DRAFT'
        allowed = {'submit':{'DRAFT','RETURNED','WITHDRAWN'},'return':{'SUBMITTED'},'review':{'SUBMITTED'},
                   'withdraw':{'SUBMITTED','RETURNED','REVIEWED','DELIVERED'},'deliver':{'REVIEWED'}}
        if state not in allowed[action]:
            raise ValueError('Action unavailable for / 当前状态不支持该操作 '+state)
        station = body.get('station') or None
        if station is not None:
            station = station_key(station)
            if station not in stations:
                raise ValueError('Station outside this run / 该河站不在本次计算中')
        requested = body.get('dependencies',[])
        if not isinstance(requested,list) or not all(isinstance(k,str) and k in inputs for k in requested):
            raise ValueError('Unknown decision input / 找不到关联输入')
        deps = {k:inputs[k] for k in requested}
        if station and 'RS/'+station in inputs:
            deps['RS/'+station]=inputs['RS/'+station]
        if 'native_inputs_and_output' in inputs:
            deps['native_inputs_and_output']=inputs['native_inputs_and_output']
        if action in ('return','review'):
            if not deps:
                raise ValueError('Select the input or station reviewed / 请选择核对的参数或断面')
            submitted = next(r for r in reversed(current) if r['action']=='submit')
            if submitted['actor'].casefold()==actor.casefold():
                raise ValueError('A second operator reviews the submission / 请由另一位经办人复核提交')
        if action=='submit':
            from .handoff import bound_package
            receipt=bound_package(model)
            if not receipt or receipt.get('summary')!=model.get('summary') or model.get('exports_need_refresh'):
                raise ValueError('Submit the calculated edition with its current packages / 请先补齐本版计算和交付包')
            latest = {}
            for row in rows:
                latest[row['edition']['project']]=row
            others=[r for k,r in latest.items() if k!=key and r['state'] not in ('SUPERSEDED','WITHDRAWN')]
            for r in others:
                if r['edition']['project'] not in lineage or r['state']!='RETURNED':
                    raise ValueError('Return or withdraw the previous submission first / 请先退回或撤回上一提交')
                append(rows,r['edition'],'supersede',actor,note=note,replacement=edition,dependencies={},station=None)
        handoff = None
        if action=='deliver':
            from .team_delivery import export
            handoff=export(key,edition,body.get('scope_token'),head(rows))
        row=append(rows,edition,action,actor,note=note,station=station,dependencies=deps,handoff=handoff)
        save(path,rows)
    return dict(event=row,head=row['token'],state=row['state'],handoff=handoff)
