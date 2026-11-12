"""One job, one owned HEC-RAS instance; never edits an already-open project."""
import sys, os, time, subprocess, traceback
from pathlib import Path
import h5py, numpy as np
import pythoncom, win32com.client.dynamic
from .common import *

BASE='Results/Steady/Output/Output Blocks/Base Output/Steady Profiles'
WANTED=['W.S. Elev','E.G. Elev','Q Total','Vel Chnl','Froude # Chl','Crit W.S.',
    'Num Trials','Std Stp Case','Min Error','L. Freeboard','R. Freeboard',
    'Q Culv Group','Q Barrel','W.S. US.','E.G. IC','E.G. OC','Culv Vel DS','Culv Vel US',
    'Culv Inv El Up','Culv Inv El Dn','Culv WS Inlet','Culv WS Outlet','Culv Full Len',
    'Q Weir','# Barrels','Q Bridge','Min Weir El','Culv Area DS','Culv Area US','Q Culv',
    'Culv Depth Blocked','Culv Inlet Mann n','Culv Outlet Mann n','Culv Length']

def verify_native(hdf, expected, profiles):
    checks={}
    with h5py.File(hdf) as h:
        groups=h['Geometry/Structures/Culvert Groups/Attributes'][:]
        if len(groups)!=len(expected['groups']):raise ValueError('Wrong culvert group count')
        names={'count':'Barrels','span_ft':'Span','rise_ft':'Rise','length_ft':'Length','us_invert_ft':'US Invert','ds_invert_ft':'DS Invert'}
        barrels=h['Geometry/Structures/Culvert Groups/Barrels/Attributes'][:]
        for gi,(actual,b) in enumerate(zip(groups,expected['groups'])):
            for key,field in names.items():
                if not np.isclose(float(actual[field]),b[key],rtol=0,atol=.002):raise ValueError('Culvert readback mismatch: '+key)
            if int(actual['Shape'])!={'circular':1,'box':2}[b['shape']]:raise ValueError('Wrong culvert shape')
            for key,field in {'chart':'Chart','scale':'Scale','culvert_n':'Mann Top','bottom_n':'Mann Bottom',
                    'bottom_n_depth_ft':'Depth for Bottom Mann','depth_blocked_ft':'Depth Blocked',
                    'entrance_loss':'Entrance Loss','exit_loss':'Exit Loss','distance_us_ft':'US Distance'}.items():
                if key in b and not np.isclose(float(actual[field]),b[key],rtol=0,atol=.002):raise ValueError('Culvert field mismatch: '+field)
            if 'name' in b and actual['Name'].decode().strip()!=b['name']:raise ValueError('Culvert group identity mismatch')
            if 'centers_ft' in b:
                subset=barrels[barrels['Culvert Group ID']==gi]
                wanted=np.asarray(b['centers_ft']);points=np.column_stack([subset['US Station'],subset['DS Station']])
                if wanted.shape!=points.shape or not np.allclose(wanted,points,rtol=0,atol=.002):raise ValueError('Barrel centerline readback mismatch')
        structures=h['Geometry/Structures/Attributes'][:]
        if len(structures)!=1 or structures[0]['Type']!=b'Culvert' or structures[0]['Culvert Groups']!=len(groups):raise ValueError('Unexpected additional bridge/opening')
        from .native_geometry import verify_road
        road_check=verify_road(structures[0],h['Geometry/Structures/Table Info'][0],h['Geometry/Structures/Profile Data'][:],expected)
        actual_names=[b.decode().strip() for b in h[BASE+'/Profile Names'][:]]
        if actual_names!=[p['id'] for p in profiles]:raise ValueError('Profile identities mismatch')
        flows=h[BASE+'/Cross Sections/Flow'][:]
        if not np.allclose(flows,np.array([p['flow_cfs'] for p in profiles])[:,None],atol=.002,rtol=0):raise ValueError('Flows mismatch')
        attrs=h['Geometry/Cross Sections/Attributes'][:]
        if len(attrs)!=expected['xs_count']:raise ValueError('Cross section count mismatch')
        if expected.get('xs_stations'):
            rs=[x['RS'].decode().strip() for x in attrs]
            if rs!=expected['xs_stations']:raise ValueError('Cross section station identities mismatch')
        if 'manning_by_section' in expected:
            info=h["Geometry/Cross Sections/Manning's n Info"][:];values=h["Geometry/Cross Sections/Manning's n Values"][:]
            if len(info)!=len(expected['manning_by_section']):raise ValueError('Manning section count mismatch')
            for (start,count),wanted in zip(info,expected['manning_by_section']):
                actual=values[start:start+count]
                if actual.shape!=np.asarray(wanted).shape or not np.allclose(actual,wanted,rtol=0,atol=.00051):raise ValueError('Manning subdivision readback mismatch')
        elif 'channel_n' in expected:
            rough=h["Geometry/Cross Sections/Manning's n Values"][:,1]
            if not np.allclose(rough.reshape(-1,3),[expected['overbank_n'],expected['channel_n'],expected['overbank_n']],rtol=0,atol=1e-6):raise ValueError('Roughness readback mismatch')
        if 'ineffective_by_section' in expected:
            wanted=expected['ineffective_by_section']
            if any(wanted):
                info=h['Geometry/Cross Sections/Ineffective Info'][:];values=h['Geometry/Cross Sections/Ineffective Blocks'][:]
                if len(info)!=len(wanted):raise ValueError('Ineffective section count mismatch')
                for (start,count),rows in zip(info,wanted):
                    actual=[[float(v[k]) for k in ['Left Sta','Right Sta','Elevation','Permanent']] for v in values[start:start+count]]
                    if len(actual)!=len(rows) or rows and not np.allclose(actual,rows,rtol=0,atol=.002):raise ValueError('Ineffective area readback mismatch')
            elif 'Geometry/Cross Sections/Ineffective Blocks' in h and len(h['Geometry/Cross Sections/Ineffective Blocks']):raise ValueError('Unexpected ineffective areas')
        if expected.get('cross_sections'):
            info=h['Geometry/Cross Sections/Station Elevation Info'][:];values=h['Geometry/Cross Sections/Station Elevation Values'][:]
            for i,section in enumerate(expected['cross_sections']):
                start,count=info[i];wanted=np.column_stack([section['station_ft'],section['elevation_ft']])
                actual=values[start:start+count]
                if actual.shape!=wanted.shape or not np.allclose(actual,wanted,rtol=0,atol=.002):raise ValueError('External station/elevation readback mismatch')
                row=attrs[i]
                for field,v in zip(['Len Left','Len Channel','Len Right'],section['reach_lengths_ft']):
                    if not np.isclose(row[field],v,rtol=0,atol=.002):raise ValueError('Reach length mismatch')
                for field,v in zip(['Left Bank','Right Bank'],section['bank_stations_ft']):
                    if not np.isclose(row[field],v,rtol=0,atol=.002):raise ValueError('Bank station mismatch')
        w=h[BASE+'/Cross Sections/Water Surface'][:]
        if not np.isfinite(w).all() or (np.abs(w)>1e30).any():raise ValueError('Invalid WSE output')
        checks=dict(profile_names=actual_names,profiles_and_flows=True,culvert_groups=len(groups),road_readback=road_check,
            barrels=[int(x['Barrels']) for x in groups],geometry_and_structure=True,no_additional_bridge=True,
            xs_count=len(attrs),roughness='verified' if 'channel_n' in expected or 'manning_by_section' in expected else 'preserved reviewed native input',
            ineffective_areas='verified' if 'ineffective_by_section' in expected else 'preserved reviewed native input')
    return checks

def controller_extract(c,project,hdf,probe_flags=None):
    profiles=c.Output_GetProfiles(0,None); variables=c.Output_Variables(0,None,None);nodes=c.Output_GetNodes(1,1,0,None,None)
    ids={name:i+1 for i,name in enumerate(variables[1])}
    save(project.parent/'output_variables.json',variables)
    trial=c.Output_NodeOutput(1,1,1,0,1,ids['W.S. Elev'])
    with h5py.File(hdf) as f: expected=float(f[BASE+'/Cross Sections/Water Surface'][0,0])
    val=float(trial[0] if isinstance(trial,tuple) else trial)
    if abs(val-expected)>.001:raise ValueError('Controller variable ordinal validation failed')
    rows=[]
    for prof,pname in enumerate(profiles[1],1):
        for n,(rs,kind) in enumerate(zip(nodes[3],nodes[4]),1):
            for flag in ((probe_flags or [0,1]) if kind else [0]):
                metrics={name:c.Output_NodeOutput(1,1,n,flag,prof,ids[name]) for name in WANTED if name in ids}
                rows.append(dict(profile=pname.strip(),station=rs.strip(),node_type=kind,updn_argument=flag,metrics=metrics))
    result=dict(project=rel(project),hdf_sha256=sha(hdf),profiles=profiles,nodes=nodes,variable_ids=ids,
        ordinal_validation=dict(controller_value=val,hdf_value=expected,matched=True),rows=rows,
        aggregation_semantics='Experimental structure flags: no group interpretation established' if probe_flags else 'Software group and representative barrel outputs; not independent per-cell solutions')
    if probe_flags:
        result['experimental_reach_output']={}
        for name in ['W.S. Elev','Q Culv Group','Q Barrel','Culv Inv El Up','Q Culv']:
            try:
                n=len(nodes[3]);result['experimental_reach_output'][name]=c.Output_ReachOutput(1,1,1,ids[name],n,
                    ['']*n,[0.]*n,[0.]*n)
            except Exception as e:result['experimental_reach_output'][name]=dict(status='UNAVAILABLE',error=str(e))
    save(project.parent/'controller_output.json',result)

def main(path):
    r=read(path);folder=path.parent;project=safe_path(ROOT,r['project']);hdf=project.with_suffix('.p01.hdf')
    if hdf.exists():raise RuntimeError('Refusing existing plan result in fresh run')
    if project.with_suffix('.LOG').exists():raise RuntimeError('Refusing existing log in fresh run')
    state=dict(run_id=r['run_id'],case_kind=r['case_kind'],started_at_utc=utc(),solver_invoked=False,
        compute_completed=False,output_identity_verified=False,status='IN_PROGRESS',stages=[],engine=r['engine'])
    def update(stage,**values):
        state.update(values);state['stages'].append(dict(stage=stage,time_utc=utc()));save(folder/'execution.json',state)
        print(stage,flush=True)
    c=None;owned_project=False
    try:
        env=os.environ.copy();env['PATH']=str(ROOT/'.tools/solver_runtime')+os.pathsep+env['PATH']
        si=subprocess.STARTUPINFO();si.dwFlags|=subprocess.STARTF_USESHOWWINDOW;si.wShowWindow=0
        app=subprocess.Popen([r['engine']['selected']['executable'],'-Embedding'],cwd=project.parent,env=env,startupinfo=si)
        update('owned_server_started',owned_app_pid=app.pid);time.sleep(2)
        pythoncom.CoInitialize()
        c=win32com.client.dynamic.Dispatch(pythoncom.CoCreateInstance(r['engine']['selected']['clsid'],None,pythoncom.CLSCTX_LOCAL_SERVER,pythoncom.IID_IDispatch))
        current=c.CurrentProjectFile()
        if current:
            state['blocking_code']='USER_PROJECT_OPEN'
            raise RuntimeError('Save and close the existing HEC-RAS project, then retry. / 请先保存并关闭当前 HEC-RAS 工程，再重试。 Existing project was not modified: '+str(current))
        update('empty_project_verified',version=c.HECRASVersion())
        c.Project_Open(str(project))
        if Path(c.CurrentProjectFile()).resolve()!=project:raise RuntimeError('Project identity mismatch')
        owned_project=True;c.Project_Save();update('roundtrip_saved')
        update('compute_invoked',solver_invoked=True)
        response=c.Compute_CurrentPlan(0,None,True);complete=bool(c.Compute_Complete())
        update('compute_returned',compute_response=response,compute_complete_flag=complete)
        if not response[0] or not complete:raise RuntimeError('HEC-RAS compute did not complete')
        if not hdf.is_file() or hdf.stat().st_mtime<datetime.fromisoformat(state['started_at_utc']).timestamp()-1:raise RuntimeError('Fresh result missing')
        if r.get('native_terrain'):
            exe=Path(r['engine']['selected']['executable']).parent/'RasProcess.exe'
            terrain=safe_path(ROOT,r['native_terrain']);geometry=project.with_suffix('.g01.hdf')
            args=[str(exe),'SetGeometryAssociation','GeometryFilename='+str(geometry),'TerrainFilename='+str(terrain)]
            association=subprocess.run(args,cwd=project.parent,capture_output=True,timeout=45)
            (folder/'terrain_association.log').write_bytes(association.stdout+association.stderr)
            if association.returncode:raise ValueError('Native geometry terrain association failed')
            with h5py.File(geometry) as gf:
                link=gf['Geometry'].attrs.get('Terrain Filename');link=link.decode() if isinstance(link,bytes) else link
            if not link or (geometry.parent/link).resolve()!=terrain:raise ValueError('Terrain association readback failed')
            update('native_terrain_associated',terrain_association=dict(args=args,relative_link=link))
        checks=verify_native(hdf,r['expected'],r['profiles']);c.Output_Initialize();controller_extract(c,project,hdf,r.get('probe_structure_flags'))
        update('identity_and_results_verified',native_field_checks=checks,compute_completed=True,output_identity_verified=True,
            output_written_this_run=True,status='COMPUTED_PENDING_QA',hdf_sha256=sha(hdf),
            native_log=item(project.with_suffix('.LOG')) if project.with_suffix('.LOG').is_file() else None)
    except Exception as e:
        update('failure',status='FAILED',error=str(e));traceback.print_exc();return 1
    finally:
        if c is not None and owned_project:
            try:
                if Path(c.CurrentProjectFile()).resolve()==project:c.Project_Close();c.QuitRas()
            except Exception as e:state['cleanup_warning']=str(e)
        state['finished_at_utc']=utc();save(folder/'execution.json',state)
    return 0

if __name__=='__main__':
    if sys.stdin.readline().strip()!='GO':raise SystemExit('Supervisor handshake missing')
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
