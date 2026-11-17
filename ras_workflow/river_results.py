"""River reach results from genuine, identity-checked HEC-RAS HDF and COM output."""
import csv
import h5py
import numpy as np
from .common import read, save, sha, item, rel
from .results import BASE, value


def extract(project, expected, config, scenario, run_id, folder):
    hdf = project.with_suffix('.p01.hdf')
    com = read(project.parent / 'controller_output.json')
    if com['hdf_sha256'] != sha(hdf):
        raise ValueError('Controller/HDF identity mismatch')
    profiles, metrics_rows, section_rows, alerts = [], [], [], []
    with h5py.File(hdf) as h:
        rs = [r['Station'].decode().strip() for r in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        infos = h['Geometry/Cross Sections/Station Elevation Info'][:]
        points = h['Geometry/Cross Sections/Station Elevation Values'][:]
        messages = '\n'.join(v.decode(errors='replace') for v in h['Results/Summary/Compute Messages (text)'][:])
        (folder / 'compute_messages.txt').write_text(messages, encoding='utf-8')
        for i, profile in enumerate(scenario['profiles']):
            name = profile['id']
            w = h[BASE + '/Cross Sections/Water Surface'][i]
            e = h[BASE + '/Cross Sections/Energy Grade'][i]
            q = h[BASE + '/Cross Sections/Flow'][i]
            if not all(np.isfinite(a).all() for a in (w,e,q)):
                raise ValueError('Nonfinite river output')
            xr = [r for r in com['rows'] if r['profile'] == name and not r['node_type']]
            if [r['station'] for r in xr] != rs:
                raise ValueError('River section COM/HDF identities differ')
            velocities = [value(r['metrics'].get('Vel Chnl', [3.4e38])) for r in xr]
            froudes = [value(r['metrics'].get('Froude # Chl', [3.4e38])) for r in xr]
            # HW/TW aliases keep the historical comparison contract; river reports label endpoints.
            metrics = dict(headwater_wse_ft=float(w[0]), headwater_egl_ft=float(e[0]), tailwater_wse_ft=float(w[-1]),
                           upstream_wse_ft=float(w[0]), downstream_wse_ft=float(w[-1]),
                           max_channel_velocity_fts=max((v for v in velocities if v is not None), default=None),
                           max_channel_froude=max((v for v in froudes if v is not None), default=None))
            wet = [rs[j] for j, (start, count) in enumerate(infos) if w[j] > min(points[start, 1], points[start + count - 1, 1])]
            rises = [dict(us=rs[j], ds=rs[j+1], rise_ft=float(e[j+1]-e[j])) for j in range(len(rs)-1) if e[j+1]-e[j] > .05]
            residual = float(np.max(np.abs(q - profile['flow_cfs'])))
            errors=[dict(rs=r['station'],error=value(r['metrics']['Min Error'])) for r in xr
                    if value(r['metrics'].get('Min Error',[3.4e38])) is not None and value(r['metrics']['Min Error'])>.3]
            critical=[r['station'] for r in xr if value(r['metrics'].get('Crit W.S.',[3.4e38])) is not None
                      and value(r['metrics'].get('W.S. Elev',[3.4e38])) is not None
                      and abs(value(r['metrics']['W.S. Elev'])-value(r['metrics']['Crit W.S.']))<.01]
            qa = dict(wet_edges=wet, egl_rises=rises, min_error_alerts=errors, critical_matches=critical,
                      full_warning_table='NOT_EXPORTED', flow_balance_residual_cfs=residual,
                      flow_balance_relative_error=residual/profile['flow_cfs'],
                      flow_check_basis='Constant-discharge section output consistency; not an independent mass-balance test')
            if wet or rises or errors or critical:
                alerts.append(dict(profile=name,wet_edges=len(wet),egl_rises=len(rises),min_errors=len(errors),critical_matches=len(critical)))
            profiles.append(dict(profile_id=name, flow_cfs=profile['flow_cfs'], metrics=metrics,
                                 headwater_rs=rs[0], tailwater_rs=rs[-1], qa=qa, culvert_groups=[]))
            for j, r in enumerate(xr):
                section_rows.append([name, rs[j], float(w[j]), float(e[j]), velocities[j], froudes[j]] +
                                    [value(r['metrics'].get(k, [3.4e38])) for k in ['L. Freeboard', 'R. Freeboard']])
            for key, v in metrics.items():
                metrics_rows.append(dict(run_id=run_id, profile_id=name, flow_cfs=profile['flow_cfs'], metric_name=key,
                    value=v, unit='ft/s' if key.endswith('fts') else 'dimensionless' if 'froude' in key else 'ft',
                    datum=expected['vertical_datum'] if key.endswith('_ft') else None, raw_hdf=rel(hdf), raw_controller=rel(project.parent/'controller_output.json'),
                    calculation_status='COMPUTED', QA_status='REVIEW_REQUIRED'))
    with (folder/'metrics.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f, fieldnames=list(metrics_rows[0]));writer.writeheader();writer.writerows(metrics_rows)
    with (folder/'cross_sections.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['profile','station','wse_ft','egl_ft','velocity_channel_fts','froude_channel','left_bank_freeboard_ft','right_bank_freeboard_ft']);writer.writerows(section_rows)
    limitations = [
        'Single-reach 1D steady flow with constant discharge within each profile; no flood hydrograph or 2D floodplain routing.',
        'Bridge structures are excluded. Boundary placement alone does not specify water level or remove bridge backwater.',
        'Surface DEM is not a measured submerged channel bed; verify the declared channel geometry basis.',
        'Full native warning export is tracked separately; hydraulic QA and engineering acceptance remain separate from compute success.',
        'No field calibration or engineering acceptance.']
    result=dict(model_type='river',run_id=run_id,scenario_id=scenario['id'],project_id=config['project_id'],case_kind=config['case_kind'],
        title=config['title'],calculation_status='COMPUTED',hydraulic_qa_status='REVIEW_REQUIRED',engineering_acceptance_status='NOT_ASSESSED',
        input_adequacy_status='SOFTWARE_VALIDATION_ONLY' if config['case_kind']=='software_validation' else 'CONDITIONAL_UNVERIFIED',
        raw_hdf=item(hdf,'real_solver_result'),raw_controller=item(project.parent/'controller_output.json'),profiles=profiles,alerts=alerts,
        datum=expected['vertical_datum'],unit='international ft',channel_geometry_basis=expected.get('channel_geometry_basis'),
        boundaries=expected.get('boundaries'),boundary_slopes=expected.get('boundary_slopes'),flow_regime=expected.get('flow_regime'),limitations=limitations)
    from .qa import diagnostics
    checked=diagnostics(result,folder/'qa')
    result.update(diagnostics=item(folder/'qa/diagnostics.json','numerical_diagnostics'),diagnostic_counts=checked['counts'])
    save(folder/'hydraulic_results.json',result)
    return result
