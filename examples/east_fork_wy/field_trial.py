"""Reproduce the station-referenced USGS East Fork calibration and blind event check."""
import argparse
import csv
import math
import sys
from pathlib import Path

import h5py

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from ras_workflow import common as c, native
from ras_workflow.qa import BASE

FT = 1 / 0.3048
GRID = 'LOCAL_CS["USGS surveyed river chainage",LOCAL_DATUM["Local survey",0],UNIT["foot",0.3048],AXIS["X",EAST],AXIS["Y",NORTH]]'


def trial(folder, spec, event, n_value, engine):
    folder.mkdir()
    observation = {r['rs']: r for r in event['observations']}
    sections = spec['sections']
    assert set(observation) == {r['rs'] for r in sections}
    ds = sections[-1]['rs']
    offset = spec['offset_m']
    boundary = (observation[ds]['stage_m'] + offset) * FT
    geometry = dict(schema_version='1.0', model_type='river', river='East Fork', reach='0220 to 0516',
                    hydraulic_unit='international_ft', horizontal_crs=GRID, map_reference='local_survey_chainage',
                    channel_geometry_basis='surveyed_channel', vertical_datum=spec['datum'],
                    flow_regime='subcritical', boundaries={'downstream': dict(type='known_stage', stages_ft=[boundary])},
                    cross_sections=[], provenance=spec['source_geometry'])
    for i, sec in enumerate(sections):
        start = sec['start_m']
        x = [(start+j)*FT for j in range(len(sec['z']))]
        z = [(offset+v)*FT for v in sec['z']]
        reach = (sec['rs']-sections[i+1]['rs'])*FT if i+1<len(sections) else 0.0
        y = sec['rs']*FT
        mid = (x[0]+x[-1])/2
        geometry['cross_sections'].append(dict(rs=sec['rs'], station_ft=x, elevation_ft=z,
            bank_stations_ft=[v*FT for v in sec['banks_m']], center_xy=[0,y],
            cutline_xy=[[mid-x[0],y],[mid-x[-1],y]], reach_lengths_ft=[reach]*3,
            expansion_contraction=spec['losses_expansion_contraction']))
    scenario = dict(id=event['role'], channel_n=n_value, overbank_n=n_value,
                    profiles=[dict(id=event['role'].upper(),flow_cfs=round(event['flow_m3s']*FT**3,3))])
    c.save(folder/'inputs.json', dict(geometry=geometry,scenario=scenario,event=event))
    project, expected = native.build(folder/'model',{'project_id':'east_fork_wy','solver_logging':'diagnostic'},
                                     scenario, geometry, survey_stationing_only=True)
    request = dict(run_id=c.unique_id(),case_kind='field_benchmark',project=c.rel(project),engine=engine,
                   expected=expected,profiles=scenario['profiles'])
    c.save(folder/'request.json',request)
    record = native.run_isolated(folder/'request.json',180)
    if not record.get('compute_completed') or not record.get('output_identity_verified'):
        raise ValueError('Native solve not verified. See '+str(folder/'execution.json'))
    hdf=project.with_suffix('.p01.hdf')
    if c.sha(hdf)!=record['hdf_sha256']:raise ValueError('Native results changed')
    ctrl=c.read(project.parent/'controller_output.json')
    controls={float(r['station']):r['metrics'] for r in ctrl['rows'] if not r['node_type']}
    rows=[]
    with h5py.File(hdf) as f:
        block=f[BASE+'/Cross Sections']
        names=[float(a['RS']) for a in f['Geometry/Cross Sections/Attributes']]
        for i,rs in enumerate(names):
            ob=observation[rs]
            stage=float(block['Water Surface'][0,i])*0.3048
            ground=geometry['cross_sections'][i]['elevation_ft']
            observed=offset+ob['stage_m']
            rows.append(dict(rs=int(rs),role='downstream forcing' if rs==ds else event['role'],
                time=ob['time'],observed_m=observed,computed_m=stage,flow_cfs=float(block['Flow'][0,i]),
                residual_m=None if rs==ds else stage-observed,wet_left=stage>ground[0]*0.3048,
                wet_right=stage>ground[-1]*0.3048,standard_step_case=controls[rs].get('Std Stp Case'),
                raw_bank_pair_m=ob.get('bank_pair_m')))
    if abs(rows[-1]['computed_m']-rows[-1]['observed_m'])>0.001:raise ValueError('Boundary readback mismatch')
    errors=[r['residual_m'] for r in rows if r['residual_m'] is not None]
    result=dict(n=n_value,flow_m3s=event['flow_m3s'],rows=rows,rmse_m=math.sqrt(sum(e*e for e in errors)/len(errors)),
                mae_m=sum(abs(e) for e in errors)/len(errors),bias_m=sum(errors)/len(errors),
                worst_m=max(map(abs,errors)),inputs=c.item(folder/'inputs.json'),native=c.item(hdf),
                execution=c.item(folder/'execution.json'),log=record.get('native_log'))
    print(event['role'],n_value,'RMSE (m)',round(result['rmse_m'],5),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration',help='Use a frozen calibration.json to score the separate event')
    args=parser.parse_args()
    spec=c.read(HERE/'training.json')
    engine=native.discover()
    if engine['status']!='READY':raise ValueError(engine['blocking_items'])
    parent=c.ROOT/'projects'/'east_fork_wy_check'
    parent.mkdir(exist_ok=True,parents=True)
    out=parent/c.unique_id()
    out.mkdir()
    if args.calibration:
        path=c.safe_path(c.ROOT,args.calibration)
        cal=c.read(path)
        if cal['training']!=c.item(HERE/'training.json') or cal['runner']!=c.item(Path(__file__)):
            raise ValueError('Training specification or runner has changed; repeat calibration')
        best=min(cal['trials'],key=lambda t:t['rmse_m'])
        if not c.intact([r[k] for r in cal['trials'] for k in ('inputs','native','execution')]) or cal['selected_n']!=best['n']:
            raise ValueError('Original calibration evidence is unavailable or changed')
        hold=c.read(HERE/'holdout.json')
        if hold['role']!='holdout' or hold['date']!=spec['holdout_date'] or hold['date']==spec['calibration']['date']:
            raise ValueError('Predeclared holdout identity mismatch')
        result=trial(out/'holdout',spec,hold,best['n'],engine)
        c.save(out/'holdout.json',dict(calibration=c.item(path),observation_source=c.item(HERE/'holdout.json'),result=result))
        rows=[dict(event=e,**r) for e,t in [('calibration',best),('holdout',result)] for r in t['rows']]
        with (out/'residuals.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    else:
        runs=[trial(out/f'n_{n:.3f}',spec,spec['calibration'],n,engine) for n in spec['candidate_n']]
        c.save(out/'calibration.json',dict(training=c.item(HERE/'training.json'),runner=c.item(Path(__file__)),
               selected_n=min(runs,key=lambda t:t['rmse_m'])['n'],trials=runs))
    print(c.rel(out),flush=True)


if __name__=='__main__':main()
