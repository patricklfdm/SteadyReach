"""Run-bound native text supplements. Never fabricates unavailable outputs."""
import base64
import copy
import re
from collections import Counter
from pathlib import Path
import h5py
from .common import ROOT, read, save, item, rel, intact, safe_path, unique_id, utc, digest
from . import app_core as core
from .qa import verified_profiles, number, BASE
from .culvert_details import parse as group_parse, _close, FIELDS
from .native_warnings import parse as warning_parse


def inspect(summary_entry,files,scope_confirmed=False):
    if not intact([summary_entry]+files):raise ValueError('Source or solver summary changed')
    summary=read(ROOT/summary_entry['path']);h=summary['hydraulics'];verified_profiles(h)
    controller=read(ROOT/h['raw_controller']['path']);hdf=ROOT/h['raw_hdf']['path']
    plan=hdf.with_name(hdf.name[:-4]).read_text(encoding='ascii')
    ids=[v.split('=',1)[1].strip() for v in plan.splitlines() if v.startswith('Short Identifier=')]
    if len(ids)!=1:raise ValueError('Ambiguous native plan identifier')
    rows=[];warnings=None;seen=set();expected=set()
    decode=lambda x:x.decode('ascii').strip()
    with h5py.File(hdf) as f:
        if not decode(f.attrs['File Version']).startswith('HEC-RAS 7.0.1 ') or decode(f.attrs['Units System'])!='US Customary':raise ValueError('Native text adapter requires inspected HEC-RAS 7.0.1 English / US Customary output')
        structures=f['Geometry/Structures/Attributes'][:];groups=f['Geometry/Structures/Culvert Groups/Attributes'][:]
        if len(structures)!=1 or not 1<=len(groups)<=10:raise ValueError('One crossing with 1–10 groups is supported')
        struct=structures[0];river,reach,station=[decode(struct[k]) for k in ('River','Reach','RS')]
        names=[decode(g['Name']) for g in groups]
        if len(set(names))!=len(names):raise ValueError('Ambiguous native group names')
        profiles={p['profile_id']:p for p in h['profiles']};expected={(p,n) for p in profiles for n in names}
        stations=[decode(a['RS']) for a in f['Geometry/Cross Sections/Attributes'][:]]
        for entry in files:
            text=(ROOT/entry['path']).read_text(encoding='utf-8-sig')
            if text.lstrip('\ufeff').startswith('Plan: '):
                parsed=group_parse(text);found=[]
                for pi,p in enumerate(h['profiles']):
                    for gi,name in enumerate(names):
                        header=f"Plan: {ids[0]}    {river}    {reach}  RS: {station}   Culv Group:  {name}   Profile: {p['profile_id']}"
                        if parsed['header']==header:found.append((pi,p,gi,name))
                if len(found)!=1:raise ValueError('Native table header does not match this run/profile/group')
                pi,p,gi,name=found[0];key=(p['profile_id'],name)
                if key in seen:raise ValueError('Duplicate profile/group export')
                seen.add(key);v=parsed['values'];g=groups[gi]
                if v['# Barrels']!=int(g['Barrels']):raise ValueError('Barrel count differs from native geometry')
                for label,field in [('Culv Inv El Up (ft)','US Invert'),('Culv Inv El Dn (ft)','DS Invert')]:_close(v[label],float(g[field]),label)
                ui,di=[stations.index(p[k]) for k in ('headwater_rs','tailwater_rs')]
                w=f[BASE+'/Cross Sections/Water Surface'][pi];eg=f[BASE+'/Cross Sections/Energy Grade'][pi]
                for label,value in [('W.S. US. (ft)',w[ui]),('W.S. DS (ft)',w[di]),('E.G. US. (ft)',eg[ui]),('E.G. DS (ft)',eg[di]),('Delta WS (ft)',w[ui]-w[di]),('Delta EG (ft)',eg[ui]-eg[di])]:_close(v[label],float(value),label)
                if v['Q Culv Group (cfs)'] is None or v['Q Barrel (cfs)'] is None:raise ValueError('Group/representative barrel flow must be present')
                if abs(v['Q Culv Group (cfs)']-v['# Barrels']*v['Q Barrel (cfs)'])>.00501*(v['# Barrels']+1):raise ValueError('Group flow differs from representative barrel flow × count')
                if gi==0:
                    matches=[r for r in controller['rows'] if r['profile']==p['profile_id'] and r['station'].strip()==station and r['node_type']=='Culv' and r['updn_argument']==0]
                    if len(matches)!=1:raise ValueError('Independent first-group controller output unavailable')
                    for label in ['Q Culv Group (cfs)','Q Barrel (cfs)','Culv Vel US (ft/s)','Culv Vel DS (ft/s)','E.G. IC (ft)','E.G. OC (ft)','Culv Full Len (ft)','Q Weir (cfs)']:
                        field=label.rsplit(' (',1)[0];_close(v[label],number(matches[0]['metrics'][field]),label)
                rows.append(dict(profile=p['profile_id'],group_id=gi,native_group=name,**{k:v[label] for k,label in FIELDS.items()},raw_fields=v,export=entry,numeric_resolution=.01))
            else:
                if warnings is not None:raise ValueError('Supply one complete native warning export')
                warnings=warning_parse(text,ids[0]);warnings['source']=entry
                if warnings['plan_label']!=ids[0]:raise ValueError('Warning plan does not match')
                for row in warnings['records']:
                    if (row['river'],row['reach'])!=(river,reach) or row['profile'] not in profiles or row['station'] not in stations+[station]:raise ValueError('Warning location/profile differs from this run')
    rows.sort(key=lambda r:(list(profiles).index(r['profile']),r['group_id']))
    return dict(schema='native_supplement_1',summary=summary_entry,run_id=h['run_id'],raw_hdf=h['raw_hdf'],files=files,
        rows=rows,missing_groups=[dict(profile=p,group=g) for p,g in sorted(expected-seen)],warnings=warnings,
        warning_scope='ALL_REQUESTED_PROFILES_USER_CONFIRMED' if warnings is not None and scope_confirmed else 'EXPORTED_LOCATIONS_ONLY' if warnings else 'NOT_EXPORTED',
        scope_confirmed=scope_confirmed,method='USER_SUPPLIED_NATIVE_TEXT_CROSSCHECKED_AGAINST_HDF_AND_COM',
        limitation='Text contains no run hash. Header, geometry, common water/energy levels and first-group values are cross-checked; origin still relies on the user selecting the correct run. Missing/blank stays null. No new solve or engineering acceptance.',
        hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED')


def validate(entry):
    if not intact([entry]):raise ValueError('Native supplement changed')
    saved=read(ROOT/entry['path']);rebuilt=inspect(saved['summary'],saved['files'],saved['scope_confirmed'])
    if saved!=rebuilt:raise ValueError('Supplement differs from reparsed source exports')
    return saved


def diagnostics(h,supplement):
    d=copy.deepcopy(read(ROOT/h['diagnostics']['path']))
    covered={(r['profile'],r['group_id']) for r in supplement['rows']}
    d['issues']=[i for i in d['issues'] if not(i['code']=='CULVERT_GROUP_DETAIL_NOT_EXTRACTED' and (i['profile'],i.get('evidence',{}).get('group_id')) in covered)]
    if supplement['warning_scope']=='ALL_REQUESTED_PROFILES_USER_CONFIRMED':
        d['issues']=[i for i in d['issues'] if i['code']!='NATIVE_WARNING_TABLE_INCOMPLETE']
    if supplement['warnings']:
        for row in supplement['warnings']['records']:
            evidence=dict(native_message=row['text'],export=supplement['warnings']['source'],first_line=row['first_line'],last_line=row['last_line'])
            code='NATIVE_MULTIPLE_CRITICAL_DEPTH' if 'multiple critical depths' in row['text'].lower() else row['code']
            d['issues'].append(dict(id=digest(row)[:16],code=code,profile=row['profile'],station=row['station'],severity=row['severity'],review_status='OPEN',evidence=evidence,
                recommended_action='Inspect this native message with the section, flow paths and model assumptions. Imported evidence does not close hydraulic QA.'))
    d.update(counts=dict(Counter(i['code'] for i in d['issues'])),warning_coverage=supplement['warning_scope'],hydraulic_qa_status='REVIEW_REQUIRED')
    d['sources']+=supplement['files']
    return d


def receive(key,body):
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision'] or body.get('run_hash')!=m.get('summary',{}).get('sha256'):raise ValueError('Result edition changed; reload before importing')
    original=m['summary'];summary=read(ROOT/original['path']);prior=summary.get('native_supplement')
    old=validate(prior) if prior else None
    if old:original=old['summary']
    files=list(old['files']) if old else [];out=core.folder(key)/'result_editions'/unique_id()
    submitted=body.get('files',[])
    if not 1<=len(submitted)<=51:raise ValueError('Choose native warning/group text exports')
    for v in submitted:
        name=Path(v['name'].replace('\\','/')).name
        if not re.fullmatch(r'[\w .()-]+\.txt',name,re.I):raise ValueError('Use a .txt export filename')
        raw=base64.b64decode(v['content'],validate=True)
        if len(raw)>2_000_000:raise ValueError('Native text export exceeds 2 MB')
        path=out/'exports'/name
        if path.exists():raise ValueError('Duplicate export filename')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);files.append(item(path,'user_native_export'))
    bundle=inspect(original,files,body.get('all_profiles') is True or bool(old and old['scope_confirmed']))
    save(out/'native_supplement.json',bundle)
    revised=copy.deepcopy(summary);revised.update(native_supplement=item(out/'native_supplement.json'),parent_summary=original,edition_created_utc=utc())
    save(out/'summary.json',revised);m.update(summary=item(out/'summary.json'),revision=m['revision']+1,exports_need_refresh=True)
    # Do not advertise reports/packages from the earlier edition as current.
    m['previous_delivery']=m.get('latest_delivery') or m.get('previous_delivery')
    m.pop('latest_reports',None);m.pop('latest_delivery',None)
    core.persist(m,'IMPORT_NATIVE_SUPPLEMENT',dict(summary=m['summary'],groups=len(bundle['rows']),warnings=len((bundle['warnings'] or {}).get('records',[]))))
    return core.view(key)
