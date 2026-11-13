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


AUTOMATIC_SCOPE='ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH'
FULL_SCOPES=('ALL_REQUESTED_PROFILES_USER_CONFIRMED',AUTOMATIC_SCOPE)


def inspect(summary_entry,files,scope_confirmed=False,automatic_receipt=None):
    if not intact([summary_entry]+files):raise ValueError('Source or solver summary changed')
    summary=read(ROOT/summary_entry['path']);h=summary['hydraulics'];verified_profiles(h)
    controller=read(ROOT/h['raw_controller']['path']);hdf=ROOT/h['raw_hdf']['path']
    plan=hdf.with_name(hdf.name[:-4]).read_text(encoding='ascii')
    ids=[v.split('=',1)[1].strip() for v in plan.splitlines() if v.startswith('Short Identifier=')]
    if len(ids)!=1:raise ValueError('Ambiguous native plan identifier')
    rows=[];warnings=None;seen=set();expected=set();display_differences=[]
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
                def compare_display(label,value,reference):
                    try:_close(v[label],value,label)
                    except ValueError:
                        # A hash-bound native export can expose display/machine differences.
                        # Retain both values and an OPEN QA issue, never call them matching.
                        # Larger discrepancies or blank/value conflicts still fail closed.
                        if not automatic_receipt or v[label] is None or value is None or abs(v[label]-value)>.01001:raise
                        display_differences.append(dict(profile=p['profile_id'],group_id=gi,station=station,field=label,
                            native_display=v[label],machine_value=value,difference=v[label]-value,reference=reference,export=entry))
                if v['# Barrels']!=int(g['Barrels']):raise ValueError('Barrel count differs from native geometry')
                for label,field in [('Culv Inv El Up (ft)','US Invert'),('Culv Inv El Dn (ft)','DS Invert')]:_close(v[label],float(g[field]),label)
                ui,di=[stations.index(p[k]) for k in ('headwater_rs','tailwater_rs')]
                w=f[BASE+'/Cross Sections/Water Surface'][pi];eg=f[BASE+'/Cross Sections/Energy Grade'][pi]
                for label,value in [('W.S. US. (ft)',w[ui]),('W.S. DS (ft)',w[di]),('E.G. US. (ft)',eg[ui]),('E.G. DS (ft)',eg[di]),('Delta WS (ft)',w[ui]-w[di]),('Delta EG (ft)',eg[ui]-eg[di])]:compare_display(label,float(value),'HDF external sections')
                if v['Q Culv Group (cfs)'] is None or v['Q Barrel (cfs)'] is None:raise ValueError('Group/representative barrel flow must be present')
                if abs(v['Q Culv Group (cfs)']-v['# Barrels']*v['Q Barrel (cfs)'])>.00501*(v['# Barrels']+1):raise ValueError('Group flow differs from representative barrel flow × count')
                if gi==0:
                    matches=[r for r in controller['rows'] if r['profile']==p['profile_id'] and r['station'].strip()==station and r['node_type']=='Culv' and r['updn_argument']==0]
                    if len(matches)!=1:raise ValueError('Independent first-group controller output unavailable')
                    for label in ['Q Culv Group (cfs)','Q Barrel (cfs)','Culv Vel US (ft/s)','Culv Vel DS (ft/s)','E.G. IC (ft)','E.G. OC (ft)','Culv Full Len (ft)','Q Weir (cfs)']:
                        field=label.rsplit(' (',1)[0];compare_display(label,number(matches[0]['metrics'][field]),'Independent first-group COM')
                rows.append(dict(profile=p['profile_id'],group_id=gi,native_group=name,**{k:v[label] for k,label in FIELDS.items()},raw_fields=v,export=entry,numeric_resolution=.01))
            else:
                if warnings is not None:raise ValueError('Supply one complete native warning export')
                warnings=warning_parse(text,ids[0]);warnings['source']=entry
                if warnings['plan_label']!=ids[0]:raise ValueError('Warning plan does not match')
                for row in warnings['records']:
                    if (row['river'],row['reach'])!=(river,reach) or row['profile'] not in profiles or row['station'] not in stations+[station]:raise ValueError('Warning location/profile differs from this run')
    rows.sort(key=lambda r:(list(profiles).index(r['profile']),r['group_id']))
    bundle=dict(schema='native_supplement_1',summary=summary_entry,run_id=h['run_id'],raw_hdf=h['raw_hdf'],files=files,
        rows=rows,missing_groups=[dict(profile=p,group=g) for p,g in sorted(expected-seen)],warnings=warnings,
        warning_scope='ALL_REQUESTED_PROFILES_USER_CONFIRMED' if warnings is not None and scope_confirmed else 'EXPORTED_LOCATIONS_ONLY' if warnings else 'NOT_EXPORTED',
        scope_confirmed=scope_confirmed,method='USER_SUPPLIED_NATIVE_TEXT_CROSSCHECKED_AGAINST_HDF_AND_COM',
        limitation='Text contains no run hash. Header, geometry, common water/energy levels and first-group values are cross-checked; origin still relies on the user selecting the correct run. Missing/blank stays null. No new solve or engineering acceptance.',
        hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED')
    if automatic_receipt:
        if scope_confirmed:raise ValueError('Automatic export cannot claim a user-attested scope')
        if not intact([automatic_receipt]):raise ValueError('Automatic export receipt changed')
        receipt=read(ROOT/automatic_receipt['path'])
        if receipt.get('schema')!='automatic_native_export_1' or receipt.get('status')!='EXPORTED_PENDING_CROSSCHECK':raise ValueError('Automatic export did not finish')
        if receipt.get('files')!=files or not intact(receipt.get('sources',[])):raise ValueError('Automatic export sources changed')
        project=hdf.with_name(hdf.name[:-8]+'.prj')
        original=[item(project.with_suffix(ext)) for ext in ('.prj','.p01','.g01','.f01','.O01','.p01.hdf')]
        if [(r['sha256'],r['size_bytes']) for r in original]!=[(r['sha256'],r['size_bytes']) for r in receipt['sources']]:raise ValueError('Automatic export is not bound to this exact computed model')
        if receipt.get('profiles')!=list(profiles) or receipt.get('group_tables')!=len(expected) or expected!=seen or warnings is None:raise ValueError('Automatic export is incomplete')
        if receipt.get('scope')!='ONE_RIVER_ONE_REACH_ONE_CULVERT_CROSSING' or receipt.get('warning_scope')!=AUTOMATIC_SCOPE:raise ValueError('Unverified automatic warning scope')
        actions=[r for r in receipt.get('trace',[]) if r.get('action')=='warning_export']
        if len(actions)!=1 or not actions[0].get('all_profiles') or (actions[0].get('river'),actions[0].get('reach'))!=(river,reach) or actions[0].get('counts')!=warnings['counts']:raise ValueError('Native warning selection trace mismatch')
        bundle.update(automatic_receipt=automatic_receipt,warning_scope=AUTOMATIC_SCOPE,
            display_differences=display_differences,
            method='OWNED_HEC_RAS_NATIVE_EXPORT_CROSSCHECKED_AGAINST_HDF_AND_COM',
            limitation='Native text was exported automatically from a verified owned HEC-RAS process, with unchanged input/output hashes. Values use native display precision. Missing/blank stays null. Export does not rerun the solver or confer engineering acceptance.')
    return bundle


def validate(entry):
    if not intact([entry]):raise ValueError('Native supplement changed')
    saved=read(ROOT/entry['path']);rebuilt=inspect(saved['summary'],saved['files'],saved['scope_confirmed'],saved.get('automatic_receipt'))
    if saved!=rebuilt:raise ValueError('Supplement differs from reparsed source exports')
    return saved


def diagnostics(h,supplement):
    d=copy.deepcopy(read(ROOT/h['diagnostics']['path']))
    covered={(r['profile'],r['group_id']) for r in supplement['rows']}
    d['issues']=[i for i in d['issues'] if not(i['code']=='CULVERT_GROUP_DETAIL_NOT_EXTRACTED' and (i['profile'],i.get('evidence',{}).get('group_id')) in covered)]
    if supplement['warning_scope'] in FULL_SCOPES:
        d['issues']=[i for i in d['issues'] if i['code']!='NATIVE_WARNING_TABLE_INCOMPLETE']
    if supplement['warnings']:
        for row in supplement['warnings']['records']:
            evidence=dict(native_message=row['text'],export=supplement['warnings']['source'],first_line=row['first_line'],last_line=row['last_line'])
            code='NATIVE_MULTIPLE_CRITICAL_DEPTH' if 'multiple critical depths' in row['text'].lower() else row['code']
            d['issues'].append(dict(id=digest(row)[:16],code=code,profile=row['profile'],station=row['station'],severity=row['severity'],review_status='OPEN',evidence=evidence,
                recommended_action='Inspect this native message with the section, flow paths and model assumptions. Imported evidence does not close hydraulic QA.'))
    for row in supplement.get('display_differences',[]):
        d['issues'].append(dict(id=digest(row)[:16],code='NATIVE_DISPLAY_MACHINE_DIFFERENCE',profile=row['profile'],station=row['station'],severity='WARNING',review_status='OPEN',evidence=row,
            recommended_action='Native display and machine value differ beyond half a display unit. Inspect both; the original HDF/COM value is retained. Export completion is not numerical agreement.'))
    d.update(counts=dict(Counter(i['code'] for i in d['issues'])),warning_coverage=supplement['warning_scope'],hydraulic_qa_status='REVIEW_REQUIRED')
    d['sources']+=supplement['files']
    return d


def attach_automatic(summary,output,receipt_entry=None,error=None):
    """Add an immutable, independently validated supplement before report authoring."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    try:
        if error:raise ValueError(error)
        if not receipt_entry or not intact([receipt_entry]):raise ValueError('Native export receipt unavailable; retry export without solving.')
        receipt=read(ROOT/receipt_entry['path'])
        if receipt.get('status')!='EXPORTED_PENDING_CROSSCHECK':raise ValueError(receipt.get('error','Native export unavailable'))
        baseline=copy.deepcopy(summary);baseline.pop('native_supplement',None);baseline.pop('automatic_native_outputs',None)
        save(output/'source_summary.json',baseline)
        bundle=inspect(item(output/'source_summary.json'),receipt['files'],automatic_receipt=receipt_entry)
        save(output/'native_supplement.json',bundle)
        summary['native_supplement']=item(output/'native_supplement.json')
        summary['automatic_native_outputs']=dict(status='COMPLETE_WITH_DIFFERENCES' if bundle['display_differences'] else 'COMPLETE',receipt=receipt_entry,display_differences=len(bundle['display_differences']),
            group_tables=len(bundle['rows']),warning_messages=len(bundle['warnings']['records']),warning_counts=bundle['warnings']['counts'])
    except Exception as e:
        summary['automatic_native_outputs']=dict(status='UNAVAILABLE',receipt=receipt_entry,error=str(e))
    return summary


def retry(key):
    """Read an isolated copy of saved native results; never recompute or edit the source."""
    import shutil
    from . import native
    m=core.model(key);summary_entry=m.get('summary')
    if not summary_entry or not intact([summary_entry]):raise ValueError('No intact result to export')
    summary=read(ROOT/summary_entry['path']);h=summary['hydraulics'];verified_profiles(h)
    source=(ROOT/h['raw_hdf']['path']).parent;request=read(source.parent/'request.json')
    engine=native.discover()
    if engine.get('status')!='READY':raise ValueError(str(engine.get('blocking_items',engine)))
    out=core.folder(key)/'result_editions'/unique_id();target=out/'export_job/project'
    target.mkdir(parents=True)
    # Native support files retain their names and contents. No prior export is copied.
    for path in source.iterdir():
        if path.is_file():shutil.copyfile(path,target/path.name)
    project=target/Path(request['project']).name
    sources=[item(project.with_suffix(ext),'native_export_source') for ext in ('.prj','.p01','.g01','.f01','.O01','.p01.hdf')]
    request.update(operation='native_export',project=rel(project),engine=engine,export_sources=sources)
    request.pop('native_terrain',None);save(out/'export_job/request.json',request)
    record=native.run_isolated(out/'export_job/request.json',90)
    revised=attach_automatic(copy.deepcopy(summary),out/'supplement',record.get('native_export'))
    status=revised['automatic_native_outputs'];m['native_export_attempt']=status
    if status['status'] not in ('COMPLETE','COMPLETE_WITH_DIFFERENCES'):
        m.update(status='RESULTS_READY',phase='DONE',errors=[]);core.persist(m,'NATIVE_EXPORT_UNAVAILABLE',status);return
    revised.update(parent_summary=summary_entry,edition_created_utc=utc());save(out/'summary.json',revised)
    m.update(summary=item(out/'summary.json'),revision=m['revision']+1,exports_need_refresh=True)
    m['previous_delivery']=m.get('latest_delivery') or m.get('previous_delivery') or (read(ROOT/m['engine_state']).get('delivery') if m.get('engine_state') else None)
    m.pop('latest_reports',None);m.pop('latest_delivery',None)
    core.persist(m,'AUTOMATIC_NATIVE_EXPORT',status)
    # One click updates reports and both packages; no second user action required.
    core.regenerate(key,'delivery')


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
