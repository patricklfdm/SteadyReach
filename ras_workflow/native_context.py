"""Retain coordinate intake evidence when an engineer supplies native inputs.

No reference library is searched. Native hydraulic inputs are copied unchanged;
the existing flow entries are reconciled, and geographic presentation needs an
explicit metadata review before it can accompany the imported model.
"""
import copy
import os
from pyproj import CRS
from .common import ROOT, finite, intact, item, read, safe_path


def reconcile(packet, configuration, scenario_id):
    scenarios=configuration.get('scenarios',[])
    scenario=next((s for s in scenarios if s['id']==scenario_id),None)
    if scenario is None:raise ValueError('Original scenario is missing')
    if len(scenarios)!=1:raise ValueError('Native handoff currently needs one intake scenario; preserve and review other scenarios separately')
    matches=[]
    for p in scenario.get('profiles',[]):
        q=p.get('flow_cfs')
        if q is None:continue
        if not finite(q) or q<=0:raise ValueError('Previously entered discharge is invalid')
        candidates=[v for v in packet['profiles'] if abs(v['flow_cfs']-q)<1e-9]
        if len(candidates)!=1:
            raise ValueError('Previously entered flow '+p['id']+' = '+str(q)+' cfs does not match one native profile. Resolve the discrepancy explicitly; no value was overwritten.')
        matches.append(dict(original=copy.deepcopy(p),native_profile=candidates[0]['id']))
    if any(scenario.get(k) is not None for k in ['channel_n','overbank_n','culvert_n']):
        raise ValueError('Previously entered roughness needs explicit reconciliation with the native section/group values before this handoff; it will not be discarded')
    return matches


def configuration(packet,review,context,folder,*,direct_start=False):
    """Return approved additions before native_review creates any model files."""
    base=context['configuration'];scenario=context['scenario_id']
    matches=reconcile(packet,base,scenario)
    sources=context['sources']
    if not intact(sources):raise ValueError('Intake or mapping source evidence changed')
    if review['project_id']!=base['project_id']:raise ValueError('Native handoff must retain the original project identity')
    mapping=review.get('mapping',{})
    if mapping.get('confirmed') is not True or not str(mapping.get('basis','')).strip():
        raise ValueError('Confirm the geographic CRS, terrain metadata and their source basis')
    crs=CRS.from_user_input(mapping.get('horizontal_crs'))
    if not crs.is_projected:raise ValueError('Native geometry needs a reviewed projected CRS')
    unit=mapping.get('dem_vertical_unit');datum=mapping.get('dem_vertical_datum')
    if unit not in ['m','US survey foot','international foot'] or not isinstance(datum,str) or not datum.strip():
        raise ValueError('Review the DEM vertical unit and datum')
    if datum.strip().casefold()!=review['vertical_datum'].strip().casefold():
        raise ValueError('DEM and model vertical datums differ; a reviewed datum transformation is required')
    terrain=context['terrain'];raster=safe_path(ROOT,terrain['raster']['path']);provenance=safe_path(ROOT,terrain['provenance']['path'])
    if not intact([terrain['raster'],terrain['provenance']]):raise ValueError('Acquired DEM or its provenance changed')
    interval=mapping.get('contour_interval',2.)
    if not finite(interval) or interval<=0:raise ValueError('Contour interval must be positive')
    # Presentation units may be converted later. No vertical datum shift occurs.
    t=dict(mode='local',raster=os.path.relpath(raster,folder),provenance=os.path.relpath(provenance,folder),
        vertical_unit=unit,vertical_datum=datum.strip(),create_native=False)
    profiles=[dict(**p,source=review['source']) for p in packet['profiles']]
    for m in matches:
        p=next(p for p in profiles if p['id']==m['native_profile'])
        p['prior_input']=m['original']
        if m['original'].get('source'):p['source']+=' | Previous intake: '+m['original']['source']
    result=dict(location=copy.deepcopy(base.get('location')),terrain=t,
        scenarios=[dict(id=scenario,profiles=profiles)],
        delivery=dict(enabled=True,horizontal_crs=crs.to_string(),contour_interval=float(interval),
            imagery=dict(mode='usgs_naip'),reviewed=not direct_start,reviewer=review.get('reviewer'),basis=mapping['basis'],
                policy='local_computation_v1' if direct_start else 'named_review'))
    return result,dict(prior_profile_matches=matches,source_context=sources,
        note='Source native hydraulics preserved; downloaded DEM and NAIP serve geographic presentation, not replacement survey sections.')
