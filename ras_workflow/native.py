"""Adapter pinned to the locally inspected and integration-tested HEC-RAS build.

Syntax is taken from USACE Examples 3/4, not inferred from filenames.
Other builds must get a new inspected adapter before execution is enabled.
"""
import os, re, shutil, subprocess, sys, time, platform
from pathlib import Path
import numpy as np
from .common import *
from .river import is_river, boundary_errors, boundary_cards

RAS_SHA='ce2ca395c68c4ee17387376ea3a7152c24db483488dced4eb96a59e85fd72985'
RUNTIME_SHA='1d1a1ae540ba132f998d60d3622f0297b6e86ae399332c3b47462d7c0f560a36'
EXECUTABLE_HASHES={
    'RasProcess.exe':'accab6ee51e8617f81f0b2ca7a488011d3f3d1eb31a58ab50a9e825c9be3292e',
    'RasMapperLib.dll':'8f246aae48a5833288d12568203919693cc15992d750514058467916a203fd7e',
    'x64/RasSteady.exe':'275bd70c19e0c5d401bbb096e269073078407e74eb123d611b6e0ec47d2fb6af'}

def inventory_blockers(matches,runtime,executables):
    blockers=[];supported=[r for r in matches if r.get('sha256')==RAS_SHA]
    if not matches:blockers.append('NO_REGISTERED_HEC_RAS_CONTROLLER')
    elif not supported:blockers.append('UNSUPPORTED_HEC_RAS_BUILD: a separately inspected adapter is required')
    elif len(supported)>1:blockers.append('AMBIGUOUS_SUPPORTED_CONTROLLER: resolve registration selection')
    if runtime.get('sha256')!=RUNTIME_SHA:blockers.append('MISSING_OR_CHANGED_PROJECT_SOLVER_RUNTIME')
    if len(supported)==1:
        for name,expected in EXECUTABLE_HASHES.items():
            if not any(r.get('name')==name and r.get('sha256')==expected for r in executables):
                blockers.append('MISSING_OR_CHANGED_ENGINE_DEPENDENCY: '+name)
    if platform.system()!='Windows' or sys.maxsize<=2**32:blockers.append('WINDOWS_64_BIT_PYTHON_REQUIRED')
    return blockers

def discover():
    if platform.system()!='Windows':return dict(status='BLOCKED',blocking_items=['WINDOWS_NATIVE_EXECUTION_REQUIRED'],checked_at_utc=utc())
    import winreg
    import win32api
    matches=[];issues=[];seen=set()
    for view in [winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY]:
        def value(path):
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,path,0,winreg.KEY_READ|view) as key:return winreg.QueryValueEx(key,'')[0]
            except OSError:return None
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'',0,winreg.KEY_READ|view) as key:
                names=[winreg.EnumKey(key,i) for i in range(winreg.QueryInfoKey(key)[0])]
        except OSError as e:issues.append('Registry view unavailable: '+str(e));continue
        for name in names:
            if not (name.startswith('RAS') and name.endswith('.HECRASController')):continue
            clsid=value(name+r'\CLSID')
            if not clsid:issues.append('Controller CLSID unavailable: '+name);continue
            server=value('CLSID\\'+clsid+r'\LocalServer32')
            if not server:issues.append('Controller LocalServer32 unavailable: '+name);continue
            quoted=re.match(r'^\s*"([^"]+)"(?:\s.*)?$',server)
            p=Path(quoted.group(1) if quoted else server.strip())
            identity=(name,clsid,str(p).lower())
            if identity in seen:continue
            seen.add(identity);version=None
            if p.is_file():
                try:
                    v=win32api.GetFileVersionInfo(str(p),'\\')
                    version='.'.join(str(i) for i in [v['FileVersionMS']>>16,v['FileVersionMS']&65535,v['FileVersionLS']>>16,v['FileVersionLS']&65535])
                except Exception as e:issues.append('Executable version read: '+str(e))
            matches.append(dict(progid=name,clsid=clsid,executable=str(p),file_version=version,sha256=sha(p) if p.is_file() else None))
    supported=[r for r in matches if r['sha256']==RAS_SHA]
    runtime=ROOT/'.tools/solver_runtime/msvcr100.dll'
    executables=[]
    if len(supported)==1:
        folder=Path(supported[0]['executable']).parent
        for name in EXECUTABLE_HASHES:
            p=folder/name
            executables.append(dict(name=name,path=str(p),sha256=sha(p) if p.is_file() else None))
    runtime_record=dict(path=rel(runtime),sha256=sha(runtime) if runtime.is_file() else None)
    blockers=inventory_blockers(matches,runtime_record,executables)
    result=dict(checked_at_utc=utc(),status='BLOCKED' if blockers else 'READY',blocking_items=blockers,discovery_notes=issues,
        adapters=matches,selected=supported[0] if len(supported)==1 else None,
        adapter_id='hec_ras_7_0_1_inspected_20261013',
        runtime=runtime_record,
        interface_evidence=item(ROOT/'ras_workflow/resources/hec_ras_701_interface.json'),executables=executables,
        os=platform.platform(),python=sys.version,python_executable=sys.executable,
        limitations=['Only the inspected executable hash is enabled','Native group/warning export requires an available Windows desktop; a failed export retains computed results and can be retried without solving. COM compute messages alone are partial.'])
    return result

def fixed(values,width=8,perline=10):
    ss=[f'{float(v):{width}.3f}' for v in values]
    # Retain the represented value when a wide station only overflows
    # because the default format appends insignificant decimal zeroes.
    ss=[v if len(v)<=width else v.rstrip('0').rstrip('.').rjust(width) for v in ss]
    if any(len(v)>width for v in ss):raise ValueError('Native fixed-width value overflow')
    return '\n'.join(''.join(ss[i:i+perline]) for i in range(0,len(ss),perline))+'\n'

def discharge_field(flow):
    """Preserve the most significant digits that fit the native eight-column field."""
    for precision in range(8, 0, -1):
        text = format(flow, f'.{precision}g')
        if len(text) <= 8:
            return text.rjust(8)
    raise ValueError('Flow fixed width overflow')


def build(folder,c,s,g,*,survey_stationing_only=False):
    from .inputs import geometry_errors
    errors=geometry_errors(g,c.get('case_kind')=='software_validation',survey_stationing_only=survey_stationing_only)
    if errors:raise ValueError('Native geometry gate: '+'; '.join(errors))
    folder.mkdir(parents=True,exist_ok=False)
    templates=ROOT/'ras_workflow/templates'
    provenance=read(templates/'manifest.json')
    if not intact(provenance['files']):raise ValueError('Native templates changed')
    river_only=is_river(g)
    xs=g['cross_sections'];struct=g.get('structure',{});road=struct.get('road',{})
    from .section_hydraulics import manning,ineffective,cards,road_profiles,manning_cards
    if river_only:
        issues=boundary_errors(g,len(s['profiles']))
        if issues:raise ValueError('; '.join(issues))
        roads={};road_min=None;expected_groups=[];ui=None
    else:
        roads=road_profiles(road);road_min=min(v[1] for rows in roads.values() for v in rows)
        from .structures import native_groups
        group_text,expected_groups=native_groups(struct['groups'],s,fixed)
        ui=next(i for i,r in enumerate(xs) if r['rs']==struct['us_xs_rs']);di=ui+1
    river=g['river'];reachname=g['reach']
    for name in [river,reachname]:
        if not name.isascii() or len(name)>16 or any(x in name for x in ',\n\r'):raise ValueError('Native river/reach must be ASCII <=16 chars without commas')
    reach_label=f'{river:<16},{reachname:<16}'
    xy=np.array([r['center_xy'] for r in xs])
    header=(templates/'MULTCULV.g01').read_text(encoding='ascii').split('Type RM Length L Ch R =')[0]
    header=re.sub(r'Geom Title=.*','Geom Title=Workflow Conditional Geometry',header)
    bounds=[xy[:,0].min()-150,xy[:,0].max()+150,xy[:,1].max()+150,xy[:,1].min()-150]
    header=re.sub(r'Viewing Rectangle=.*','Viewing Rectangle='+','.join(str(v) for v in bounds),header)
    text=header[:header.index('River Reach=')]+'River Reach='+reach_label+'\n'
    text+='Reach XY= '+str(len(xy))+'\n'+fixed(xy.ravel(),16,4)+'Rch Text X Y=0,0\nReverse River Text= 0\n\n'
    for i,r in enumerate(xs):
        text+=f"Type RM Length L Ch R = 1 ,{r['rs']:.2f},"+','.join(f'{v:.3f}' for v in r['reach_lengths_ft'])+'\n'
        text+='BEGIN DESCRIPTION:\nExternal XS from explicit reviewed geometry input\nEND DESCRIPTION:\n'
        cut=r['cutline_xy'];text+=f'XS GIS Cut Line={len(cut)}\n'+fixed(np.array(cut).ravel(),16,4)
        text+=f"#Sta/Elev= {len(r['station_ft'])}\n"+fixed(np.column_stack([r['station_ft'],r['elevation_ft']]).ravel())
        left,right=r['bank_stations_ft']
        rough=manning(r,s)
        text+='#Mann= '+str(len(rough))+' , 0 , 0\n'+manning_cards(rough,fixed)
        text+=cards(r,fixed)
        text+=f'Bank Sta={left:.3f},{right:.3f}\nXS Rating Curve= 0 ,0\nExp/Cntr='+','.join(str(v) for v in r['expansion_contraction'])+'\n\n'
        if i==ui:
            text+=f"Type RM Length L Ch R = 2 ,{struct['rs']:.2f},,,\nBEGIN DESCRIPTION:\nConditional structure; provenance in input snapshot\nEND DESCRIPTION:\nBridge Culvert-0,0,1,-1, 0\n"
            text+='Deck Dist Width WeirC Skew NumUp NumDn MinLoCord MaxHiCord MaxSubmerge Is_Ogee\n'
            text+=f"{road['distance_us_ft']:.3f},{road['width_ft']},{road['weir_coefficient']},0,{len(roads['upstream'])},{len(roads['downstream'])},{road_min:.3f}, ,0.95,0,2,2,,\n"
            for rows in roads.values():
                n=len(rows);blanks=''.join('        '*min(10,n-j)+'\n' for j in range(0,n,10))
                text+=fixed([v[0] for v in rows])+fixed([v[1] for v in rows])+blanks
            text+=group_text
            text+=f"BC Design=,, 0 ,, 0 ,,,,,,\nBC HTab HWMax={max(v[1] for rows in roads.values() for v in rows)+3:.3f}\nBC Use User HTab Curves=0\nBC User HTab FreeFlow(D)= 0\n\n"
    text+='Chan Stop Cuts=-1\nUse User Specified Reach Order=0\nUser Specified Reach Order='+reach_label+'\nGIS Ratio Cuts To Invert=-1\n'
    (folder/'Model.g01').write_text(text,encoding='ascii')
    prj=(templates/'MULTCULV.prj').read_text(encoding='ascii')
    (folder/'Model.prj').write_text(re.sub(r'Proj Title=.*','Proj Title=Workflow '+c['project_id'],prj),encoding='ascii')
    plan=(templates/'MULTCULV.P01').read_text(encoding='ascii')
    plan=re.sub(r'Plan Title=.*','Plan Title=Workflow '+s['id'],plan)
    regime=g.get('flow_regime','mixed')
    plan=re.sub(r'Short Identifier=.*','Short Identifier=Workflow',plan).replace('Subcritical Flow',{'mixed':'Mixed Flow','subcritical':'Subcritical Flow'}[regime])
    for key in ['Global Log Level','Log Output Level']:
        if len(re.findall(r'^'+key+'=.*$',plan,re.M))!=1:raise ValueError('Inspected log setting missing from template')
        mode=c.get('solver_logging','off')
        if mode not in ['off','diagnostic']:raise ValueError('solver_logging must be off or diagnostic')
        plan=re.sub(r'^'+key+'=.*$',key+('= 5 ' if mode=='diagnostic' else '= 0 '),plan,flags=re.M)
    (folder/'Model.p01').write_text(plan,encoding='ascii')
    pp=s['profiles'];flow='Flow Title=Workflow '+s['id']+'\nNumber of Profiles= '+str(len(pp))+'\nProfile Names='+','.join(p['id'] for p in pp)+'\n'
    flow+=f"River Rch & RM={river},{reachname},{xs[0]['rs']:.2f}\n"
    vals=[discharge_field(p['flow_cfs']) for p in pp]
    flow+='\n'.join(''.join(vals[i:i+10]) for i in range(0,len(vals),10))+'\n'
    for i in range(len(pp)):
        flow+=f"Boundary for River Rch & Prof#={river},{reachname}, {i+1}\n"
        if river_only:
            flow+=boundary_cards(g,i)
            continue
        flow+=('Up Type= 0\n' if regime=='subcritical' else f"Up Type= 3\nUp Slope={g['boundary_slopes']['upstream']:.8f}\n")
        flow+=f"Dn Type= 3\nDn Slope={g['boundary_slopes']['downstream']:.8f}\n"
    (folder/'Model.f01').write_text(flow,encoding='ascii')
    expected=dict(model_type=g.get('model_type','culvert'),groups=expected_groups,
        xs_count=len(xs),xs_stations=[f"{r['rs']:.2f}" for r in xs],channel_n=s['channel_n'],overbank_n=s['overbank_n'],culvert_n=s.get('culvert_n'),
        road_profiles=roads,manning_by_section=[manning(r,s) for r in xs],ineffective_by_section=[ineffective(r) for r in xs],
        weir_minimum_override_ft=road_min,
        vertical_datum=g['vertical_datum'],cross_sections=xs,channel_geometry_basis=g.get('channel_geometry_basis'),boundaries=g.get('boundaries'),boundary_slopes=g.get('boundary_slopes'),flow_regime=regime)
    if river_only:
        expected.update(us_xs_rs=f"{xs[0]['rs']:.2f}",ds_xs_rs=f"{xs[-1]['rs']:.2f}")
    else:
        expected.update(road_width_ft=road['width_ft'],road_min_ft=road_min,us_xs_rs=f"{struct['us_xs_rs']:.2f}",ds_xs_rs=f"{struct['ds_xs_rs']:.2f}",structure_rs=f"{struct['rs']:.2f}")
    return folder/'Model.prj',expected

def import_native(folder,config_path,c):
    p=safe_path(config_path.parent,c['native_project']);folder.mkdir(parents=True,exist_ok=False)
    for ext in ['.prj','.g01','.p01','.f01']:
        source=p.with_suffix(ext);shutil.copyfile(source,folder/source.name)
    prj=folder/p.name
    if 'Current Plan=p01' not in prj.read_text(encoding='ascii'):raise ValueError('Native import requires explicit p01')
    plan=prj.with_suffix('.p01').read_text(encoding='ascii')
    if 'Geom File=g01' not in plan or 'Flow File=f01' not in plan:raise ValueError('Native plan references unsupported inputs')
    return prj,c['expected_native']

def run_isolated(request_path, timeout):
    """Windows Job Object contains only this worker and its newly launched descendants.
    Worker waits for GO until it is assigned. A timeout closes only this job.
    """
    import win32job, win32api
    from .native_session import session_lock
    with session_lock(),lock(ROOT/'status/workflow_solver.lock'):
        request_path=Path(request_path);folder=request_path.parent
        job=win32job.CreateJobObject(None,'Local\\HecWorkflow_'+unique_id())
        limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
        try:
            with (folder/'worker_stdout.log').open('wb') as out, (folder/'worker_stderr.log').open('wb') as err:
                proc=subprocess.Popen([sys.executable,'-m','ras_workflow.worker',str(request_path)],cwd=ROOT,
                    stdin=subprocess.PIPE,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    win32job.AssignProcessToJobObject(job,proc._handle)
                    proc.stdin.write(b'GO\n');proc.stdin.close()
                    code=proc.wait(timeout=timeout)
                    state='EXITED'
                except subprocess.TimeoutExpired:
                    state='TIMEOUT';code=None
                except Exception:
                    # It cannot launch HEC-RAS before GO; terminating this worker is scoped.
                    proc.terminate();proc.wait(timeout=10);raise
        finally:
            win32api.CloseHandle(job)
        if state=='TIMEOUT':proc.wait(timeout=15)
        result=dict(status=state,returncode=code,timeout_seconds=timeout,finished_at_utc=utc(),worker_pid=proc.pid,
                    cleanup='Windows job closed; only owned worker descendants affected')
        save(folder/'supervisor.json',result)
        record=read(folder/'execution.json') if (folder/'execution.json').is_file() else {}
        if (state=='TIMEOUT' or code!=0) and record.get('compute_completed') and record.get('output_identity_verified'):
            # Only an interruption after the verified solve may be downgraded.
            # Extraction still independently verifies the HDF/controller hashes.
            record.update(native_export_error='Native export interrupted; verified calculation retained. Retry export without solving.',native_export_interrupted=True)
            save(folder/'execution.json',record)
            return record
        if state=='TIMEOUT' or code!=0:
            execution=read(folder/'execution.json') if (folder/'execution.json').is_file() else {}
            if execution.get('blocking_code')=='USER_PROJECT_OPEN':raise RuntimeError(execution['error'])
            detail=str(execution.get('error') or '').strip()
            raise RuntimeError('Native worker '+state+(' · '+detail[:1000] if detail else '')+'; see '+rel(folder/'worker_stderr.log'))
        if read(request_path).get('operation')=='native_export':return record
        if not record.get('compute_completed') or not record.get('output_identity_verified'):raise RuntimeError('Fresh matching compute was not verified')
        return record
