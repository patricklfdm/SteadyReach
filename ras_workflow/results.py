import csv, math
import h5py, numpy as np
from .common import *

BASE='Results/Steady/Output/Output Blocks/Base Output/Steady Profiles'

def value(v):
    v=float(v[0] if isinstance(v,(list,tuple)) else v)
    return v if math.isfinite(v) and abs(v)<1e30 else None

def extract(project,expected,config,scenario,run_id,folder):
    if expected.get('model_type')=='river':
        from .river_results import extract as river_extract
        return river_extract(project,expected,config,scenario,run_id,folder)
    hdf=project.with_suffix('.p01.hdf');com=read(project.parent/'controller_output.json')
    if com['hdf_sha256']!=sha(hdf):raise ValueError('Controller/HDF identity mismatch')
    from .native_log import extract as extract_log, supplement
    log_result=extract_log(project,expected,scenario['profiles'])
    save(folder/'native_log_results.json',log_result)
    rows=[];profiles=[];alerts=[]
    with h5py.File(hdf) as h:
        rs=[v['Station'].decode().strip() for v in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        ui=rs.index(expected['us_xs_rs']);di=rs.index(expected['ds_xs_rs'])
        station_info=h['Geometry/Cross Sections/Station Elevation Info'][:];points=h['Geometry/Cross Sections/Station Elevation Values'][:]
        crest=float(h['Geometry/Structures/Attributes'][0]['Weir Min Elevation'])
        crest_source='Geometry/Structures/Attributes/Weir Min Elevation'
        if 'road_profiles' in expected:
            from .native_geometry import verify_road
            table=h['Geometry/Structures/Table Info'][0];values=h['Geometry/Structures/Profile Data'][:]
            verify_road(h['Geometry/Structures/Attributes'][0],table,values,expected)
            levels=[]
            for side in ['US','DS']:
                start=int(table[side+' BR Weir Profile (Index)']);count=int(table[side+' BR Weir Profile (Count)'])
                levels.extend(values[start:start+count,1].tolist())
            crest=min(levels);crest_source='minimum of verified US/DS Geometry/Structures/Profile Data road profiles'
        if not math.isfinite(crest):raise ValueError('Road crest unavailable; supply source-bound road profiles for verification')
        rawmsg=h['Results/Summary/Compute Messages (text)'][:]
        messages='\n'.join(v.decode(errors='replace') for v in rawmsg)
        (folder/'compute_messages.txt').write_text(messages,encoding='utf-8')
        for pi,p in enumerate(scenario['profiles']):
            w=h[BASE+'/Cross Sections/Water Surface'][pi];eg=h[BASE+'/Cross Sections/Energy Grade'][pi]
            cr=next(r for r in com['rows'] if r['profile']==p['id'] and r['node_type']=='Culv' and r['updn_argument']==0)
            m={k:value(v) for k,v in cr['metrics'].items()}
            from .structures import group_outputs,total_culvert_flow
            group_rows=group_outputs(expected['groups'],m,float(w[ui]));single=len(group_rows)==1
            lp=next((v for v in log_result['profiles'] if v['profile_id']==p['id']),None)
            if lp:group_rows=supplement(group_rows,lp)
            metrics=dict(headwater_wse_ft=float(w[ui]),headwater_egl_ft=float(eg[ui]),tailwater_wse_ft=float(w[di]),
                culvert_group_flow_cfs=m.get('Q Culv Group'),representative_barrel_flow_cfs=m.get('Q Barrel'),
                inlet_velocity_fts=m.get('Culv Vel US'),outlet_velocity_fts=m.get('Culv Vel DS'),
                roadway_flow_software_cfs=m.get('Q Weir'),road_freeboard_ft=crest-float(w[ui]),
                inlet_control_egl_ft=m.get('E.G. IC'),outlet_control_egl_ft=m.get('E.G. OC'),
                full_flow_length_ft=m.get('Culv Full Len'))
            metrics['culvert_total_flow_cfs'],total_basis=total_culvert_flow(expected['groups'],m)
            if lp and not single:
                metrics['culvert_total_flow_cfs']=lp['total_flow_cfs'];total_basis='NATIVE_LOG_FINAL_TOTAL_PRINTED_0.1_CFS'
            metrics['hw_over_d']=group_rows[0]['hw_over_d'] if single else None
            if not single:
                for key in ['culvert_group_flow_cfs','representative_barrel_flow_cfs','inlet_velocity_fts','outlet_velocity_fts',
                            'inlet_control_egl_ft','outlet_control_egl_ft','full_flow_length_ft']:metrics[key]=None
            control=None
            if single and m.get('E.G. IC') is not None and m.get('E.G. OC') is not None:control='inlet' if m['E.G. IC']>m['E.G. OC'] else 'outlet'
            wet=[rs[i] for i,(start,n) in enumerate(station_info) if w[i]>min(points[start,1],points[start+n-1,1])]
            energy=[dict(us=rs[i],ds=rs[i+1],rise_ft=float(eg[i+1]-eg[i])) for i in range(len(rs)-1) if eg[i+1]-eg[i]>.05]
            xr=[r for r in com['rows'] if r['profile']==p['id'] and not r['node_type']]
            errs=[dict(rs=r['station'],min_error_ft=value(r['metrics']['Min Error'])) for r in xr if value(r['metrics'].get('Min Error',[3.4e38])) is not None and value(r['metrics']['Min Error'])>.3]
            crit=[r['station'] for r in xr if value(r['metrics'].get('Crit W.S.',[3.4e38])) is not None and abs(value(r['metrics']['W.S. Elev'])-value(r['metrics']['Crit W.S.']))<.01]
            residual=None
            q_culvert=metrics['culvert_total_flow_cfs']
            # A conservation-derived total cannot independently verify continuity.
            if (single or lp) and q_culvert is not None and m.get('Q Weir') is not None:
                residual=p['flow_cfs']-q_culvert-m['Q Weir']
            qa=dict(wet_edges=wet,egl_rises=energy,min_error_alerts=errs,critical_matches=crit,
                full_warning_table='NOT_EXPORTED',flow_balance_residual_cfs=residual,
                flow_balance_relative_error=None if residual is None else abs(residual)/p['flow_cfs'])
            profiles.append(dict(profile_id=p['id'],flow_cfs=p['flow_cfs'],metrics=metrics,control_inferred_from_software_egl=control,
                headwater_rs=rs[ui],tailwater_rs=rs[di],qa=qa,culvert_groups=group_rows,culvert_total_flow_basis=total_basis))
            if wet or energy or errs or crit:alerts.append(dict(profile=p['id'],wet_edges=len(wet),egl_rises=len(energy),min_errors=len(errs),critical_matches=len(crit)))
            for name,v in metrics.items():
                unit='cfs' if name.endswith('cfs') else ('ft/s' if name.endswith('fts') else ('dimensionless' if name=='hw_over_d' else 'ft'))
                com_fields={'culvert_group_flow_cfs':'Q Culv Group','representative_barrel_flow_cfs':'Q Barrel','inlet_velocity_fts':'Culv Vel US','outlet_velocity_fts':'Culv Vel DS','roadway_flow_software_cfs':'Q Weir','inlet_control_egl_ft':'E.G. IC','outlet_control_egl_ft':'E.G. OC','full_flow_length_ft':'Culv Full Len'}
                com_fields['culvert_total_flow_cfs']='Q Culv Group' if single else 'Q Total - observed Q Weir (derived); null when unavailable'
                raw={'headwater_wse_ft':BASE+'/Cross Sections/Water Surface','headwater_egl_ft':BASE+'/Cross Sections/Energy Grade','tailwater_wse_ft':BASE+'/Cross Sections/Water Surface','road_freeboard_ft':'Geometry/Structures/Attributes/Weir Min Elevation minus upstream WSE','hw_over_d':'(upstream WSE - group US Invert) / group Rise'}.get(name,'controller_output.json / rows / metrics / '+com_fields.get(name,name))
                if name=='road_freeboard_ft':raw=crest_source+' minus upstream WSE'
                from_log=bool(lp and not single and name=='culvert_total_flow_cfs')
                if from_log:raw='Final Q-CULVERT; printed resolution 0.1 cfs; native_log_results.json'
                rows.append(dict(run_id=run_id,scenario_id=scenario['id'],profile_id=p['id'],flow_cfs=p['flow_cfs'],calculation_status='COMPUTED',
                    evidence_grade=config['case_kind'],location=config['project_id'],station=rs[di] if name=='tailwater_wse_ft' else rs[ui],
                    metric_name=name,value=v,unit=unit,datum=expected.get('vertical_datum') if 'wse' in name or 'egl' in name else None,raw_result_path=log_result['source']['path'] if from_log else rel(hdf),raw_field=raw,
                    extraction_method='hash-bound native log; COM cross-checked' if from_log else 'verified HDF/COM adapter',aggregation_basis=total_basis if name=='culvert_total_flow_cfs' else 'single-group only; null when multiple' if name in com_fields and name!='roadway_flow_software_cfs' else 'external XS or structure',
                    QA_status='REVIEW_REQUIRED',critical_assumptions='see input snapshot',limitation='uncalibrated; engineering acceptance NOT_ASSESSED'))
    with (folder/'metrics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (folder/'cross_sections.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['profile','station','wse_ft','egl_ft','velocity_channel_fts','froude_channel','left_bank_freeboard_ft','right_bank_freeboard_ft'])
        for r in com['rows']:
            if not r['node_type']:writer.writerow([r['profile'],r['station']]+[value(r['metrics'].get(k,[3.4e38])) for k in ['W.S. Elev','E.G. Elev','Vel Chnl','Froude # Chl','L. Freeboard','R. Freeboard']])
    with (folder/'culvert_groups.csv').open('w',newline='',encoding='utf-8-sig') as f:
        group_table=[dict(run_id=run_id,profile_id=p['profile_id'],raw_controller=rel(project.parent/'controller_output.json'),
                          raw_native_log=log_result.get('source',{}).get('path') if 'native_log_flow_cfs' in r else None,
                          log_extraction=rel(folder/'native_log_results.json') if 'native_log_flow_cfs' in r else None,**r) for p in profiles for r in p['culvert_groups']]
        writer=csv.DictWriter(f,fieldnames=list(group_table[0]));writer.writeheader();writer.writerows(group_table)
    result=dict(run_id=run_id,scenario_id=scenario['id'],project_id=config['project_id'],case_kind=config['case_kind'],
        title=config['title'],calculation_status='COMPUTED',hydraulic_qa_status='REVIEW_REQUIRED',engineering_acceptance_status='NOT_ASSESSED',
        input_adequacy_status='OFFICIAL_BENCHMARK' if config['case_kind']=='official_benchmark' else 'SOFTWARE_VALIDATION_ONLY' if config['case_kind']=='software_validation' else 'CONDITIONAL_UNVERIFIED',
        raw_hdf=item(hdf,'real_solver_result'),raw_controller=item(project.parent/'controller_output.json'),profiles=profiles,alerts=alerts,
        native_log=item(folder/'native_log_results.json'),native_log_status=log_result['status'],
        datum=expected.get('vertical_datum'),unit=config.get('native_length_unit','international ft'),road_crest_ft=crest,road_crest_source=crest_source,
        limitations=['Full GUI warning table not exported; compute messages and numerical alerts retained',
            'Missing roadway flow remains null, never changed to zero','Same-group representative barrel output is not independent per-barrel solving',
            'COM detailed culvert fields expose only the first group; verified final native log flow may supplement other groups at 0.1 cfs resolution; additional velocities remain null',
            'COM Q Culv includes roadway flow in the verified overtopping example and is not used as all-group culvert flow',
            'No field calibration or engineering acceptance','1D extent and flow paths require engineering review'])
    from .qa import diagnostics
    diagnostic_result=diagnostics(result,folder/'qa')
    result['diagnostics']=item(folder/'qa/diagnostics.json','numerical_diagnostics')
    result['diagnostic_counts']=diagnostic_result['counts']
    save(folder/'hydraulic_results.json',result)
    return result
