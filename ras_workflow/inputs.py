"""Explicit inputs and gates. No site parameters are supplied by the engine."""
from pathlib import Path
import math
import numpy as np
from pyproj import CRS
from .common import *

def template(site_id, lat, lon):
    identifier(site_id)
    if not finite(lat) or not finite(lon) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Invalid WGS84 latitude/longitude')
    return dict(schema_version='1.0', project_id=site_id, title=site_id,
        case_kind='site_conditional', location=dict(latitude=lat, longitude=lon, source='user_coordinate', crossing_confirmed=False),
        terrain=dict(mode='usgs', buffer_m=300, max_download_bytes=600_000_000, dataset_contains='1 meter', selected_source_ids=None),
        delivery=dict(enabled=True,imagery=dict(mode='usgs_naip')),
        geometry=None, geometry_review=None, authorization=None,
        scenarios=[dict(id='q100', profiles=[dict(id='Q100', flow_cfs=None, source=None)],
            channel_n=None, overbank_n=None, culvert_n=None, parameter_source=None)],
        engineering_acceptance='NOT_ASSESSED')

def load(config_path):
    path = safe_path(ROOT, config_path); c = read(path)
    if c.get('schema_version') != '1.0': raise ValueError('Unsupported project schema')
    identifier(c['project_id'])
    if c.get('case_kind') not in ['site_conditional', 'official_benchmark','software_validation']:
        raise ValueError('Unsupported case_kind')
    if c.get('solver_logging','off') not in ['off','diagnostic']:raise ValueError('solver_logging must be off or diagnostic')
    if c.get('native_project') and 'solver_logging' in c:raise ValueError('Imported native plans preserve their own inspected logging settings; do not override solver_logging')
    if 'native_length_unit' in c and (not c.get('native_project') or c['native_length_unit'] not in ['international ft','US survey foot']):raise ValueError('native_length_unit requires an imported native model and an explicit supported unit')
    ids = [identifier(s['id']) for s in c.get('scenarios', [])]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate scenario id')
    loc = c.get('location')
    if loc:
        if not all(finite(loc.get(k)) for k in ['latitude','longitude']): raise ValueError('Invalid coordinates')
        if not (-90 <= loc['latitude'] <= 90 and -180 <= loc['longitude'] <= 180): raise ValueError('Coordinate range')
    for key in ['geometry', 'authorization', 'native_project']:
        if c.get(key): safe_path(path.parent, c[key])
    return path, c

def dependencies(path, c):
    files = [path]
    for key in ['geometry','authorization','native_project','reference_results','benchmark_preparation','configuration_approval','native_import_review']:
        if c.get(key): files.append(safe_path(path.parent, c[key]))
    t = c.get('terrain', {})
    for key in ['raster','provenance']:
        if t.get(key): files.append(safe_path(path.parent, t[key]))
    if c.get('section_workflow'):
        spec_path=safe_path(path.parent,c['section_workflow']['spec']);files.append(spec_path)
        spec=read(spec_path)
        if spec.get('alignment_spec'):files.append(safe_path(path.parent,spec['alignment_spec']))
        files.extend(safe_path(ROOT,v['path']) for v in spec.get('vertical_review',{}).get('sources',[]))
    if c.get('native_project'):
        p = safe_path(path.parent, c['native_project'])
        # Only this explicitly supported plan; unknown plans are blocked, never guessed.
        files.extend(p.with_suffix(s) for s in ['.g01','.f01','.p01'])
    for p in files:
        if not p.is_file(): raise ValueError('Input missing: ' + rel(p))
    return [item(p,'input') for p in sorted(set(files))]

def geometry_errors(g,allow_synthetic=False):
    from .geometry_qa import spatial_issues, review_errors
    errors=[]
    def need(test, msg):
        if not test: errors.append(msg)
    need(g.get('approved_for_model') is not False and g.get('status') not in ['DRAFT_REQUIRES_REVIEW','REVIEW_REQUIRED'],
         'Unreviewed geometry candidate cannot be a model input')
    need(g.get('schema_version') == '1.0', 'geometry schema_version must be 1.0')
    need(g.get('hydraulic_unit') == 'international_ft', 'hydraulic_unit must be international_ft')
    need(bool(g.get('vertical_datum')), 'vertical_datum is missing')
    for key in ['river','reach']:
        value=g.get(key)
        need(isinstance(value,str) and 0<len(value)<=16 and value.isascii() and not any(x in value for x in ',\n\r'),'Native '+key+' name must be ASCII 1..16 characters without commas/newlines')
    try:
        crs=CRS.from_user_input(g['horizontal_crs']); need(crs.is_projected, 'Projected GIS CRS required')
    except Exception: errors.append('Invalid horizontal_crs')
    xs=g.get('cross_sections',[]); need(len(xs)>=4,'At least four external sections required')
    stations=[r.get('rs') for r in xs]
    need(all(finite(v) for v in stations), 'RS must be finite numeric identifiers')
    if all(finite(v) for v in stations): need(all(a>b for a,b in zip(stations,stations[1:])), 'RS must decrease downstream')
    if all(finite(v) for v in stations): need(len(set(round(v,2) for v in stations))==len(stations),'Builder RS identifiers must remain unique at 0.01 ft precision')
    for i,r in enumerate(xs):
        a=np.array(r.get('station_ft',[])); z=np.array(r.get('elevation_ft',[]))
        need(len(a)==len(z) and len(a)>=3,f'XS {i}: station/elevation lengths')
        if not(len(a)==len(z) and len(a)>=3): continue
        need(bool(np.isfinite(a).all() and np.isfinite(z).all()),f'XS {i}: NoData/nonfinite')
        need(bool(np.all(np.diff(a)>0)),f'XS {i}: station order')
        b=r.get('bank_stations_ft') or []
        need(len(b)==2 and all(finite(v) for v in b) and a[0]<b[0]<b[1]<a[-1],f'XS {i}: bank stations')
        if len(b)==2 and all(finite(v) for v in b) and np.isfinite(a).all():
            native_stations={round(float(v),3) for v in a}
            need(all(round(v,3) in native_stations for v in b),f'XS {i}: banks must be explicit station/elevation points')
            need(len(native_stations)==len(a),f'XS {i}: station points collide at native 0.001 ft precision')
        lengths=r.get('reach_lengths_ft') or []
        need(len(lengths)==3 and all(finite(v) and (v>0 if i<len(xs)-1 else v==0) for v in lengths),f'XS {i}: three reach lengths')
        need(len(r.get('cutline_xy',[]))>=2,f'XS {i}: cutline missing')
        center=r.get('center_xy') or []
        need(isinstance(center,list) and len(center)==2 and all(finite(v) for v in center),f'XS {i}: reviewed flowline center_xy pair required')
        cutline=r.get('cutline_xy') or []
        need(isinstance(cutline,list) and all(isinstance(p,list) and len(p)==2 and all(finite(v) for v in p) for p in cutline),f'XS {i}: finite cutline coordinate pairs required')
        losses=r.get('expansion_contraction') or []
        need(len(losses)==2 and all(finite(v) and 0<=v<=1 for v in losses),f'XS {i}: loss coefficients required')
        from .section_hydraulics import errors as hydraulic_errors
        errors.extend(f'XS {i}: '+v for v in hydraulic_errors(r))
    s=g.get('structure') or {}; groups=s.get('groups',[])
    need(1<=len(groups)<=10,'Builder requires 1..10 explicit culvert groups')
    names=[b.get('name',f'Group {i+1}') for i,b in enumerate(groups)]
    need(len(names)==len(set(names)),'Culvert group names must be unique')
    need(all(isinstance(n,str) and n.isascii() and 0<len(n)<=12 and not any(x in n for x in ',\n\r') for n in names),'Culvert group names must be ASCII 1..12 characters without commas/newlines')
    need(all(finite(s.get(k)) for k in ['rs','us_xs_rs','ds_xs_rs']),'Structure and face river stations must be finite')
    if all(finite(s.get(k)) for k in ['rs','us_xs_rs','ds_xs_rs']):
        need(round(s['us_xs_rs'],2)>round(s['rs'],2)>round(s['ds_xs_rs'],2),'Structure river station must lie between face sections at native precision')
    if finite(s.get('us_xs_rs')) and finite(s.get('ds_xs_rs')) and s['us_xs_rs'] in stations and s['ds_xs_rs'] in stations:
        ui=stations.index(s['us_xs_rs']); di=stations.index(s['ds_xs_rs'])
        need(di==ui+1 and ui>=1 and di<len(xs)-1,'Four functional structure sections must bracket adjacent faces')
    else: ui=None;errors.append('Explicit US/DS face sections required')
    for b in groups:
        need(b.get('shape') in ['box','circular'], 'Supported shapes: box and circular')
        for k in ['span_ft','rise_ft','length_ft','distance_us_ft']:
            need(finite(b.get(k)) and b[k]>0, 'Invalid/missing '+k)
        for k in ['us_invert_ft','ds_invert_ft','entrance_loss','exit_loss']:
            need(finite(b.get(k)), 'Invalid/missing '+k)
        for k in ['entrance_loss','exit_loss']:
            need(finite(b.get(k)) and b[k]>=0,'Nonnegative '+k+' required')
        need(isinstance(b.get('count'),int) and 1<=b['count']<=25,'barrel count 1..25')
        need(b.get('chart_scale') in ([[8,1],[8,2],[10,2]] if b.get('shape')=='box' else [[1,1]]),'Chart/scale outside validated adapter')
        need(bool(b.get('bottom_type')) and bool(b.get('inlet_description')),'Floor and inlet description required')
        blocked=b.get('depth_blocked_ft');rise=b.get('rise_ft');bottom_depth=b.get('bottom_n_depth_ft',0.)
        need(finite(blocked) and finite(rise) and 0<=blocked<rise,'Explicit depth blocked must be >=0 and less than rise; full closure uses an explicit removed-barrel scenario')
        need(finite(bottom_depth) and finite(rise) and finite(blocked) and blocked<=bottom_depth<=rise,'Bottom roughness depth must explicitly cover blockage and stay within rise')
        if finite(blocked) and blocked>0:
            need('mann_bottom' in b and bool(b.get('blockage_basis')),'Blocked/sediment scenario requires explicit bottom roughness and provenance')
        for k in ['mann_top','mann_bottom']:
            if k in b:need(finite(b[k]) and 0<b[k]<1,'Invalid '+k)
        need(b.get('evidence_class') not in ([None,'missing'] if allow_synthetic else [None,'missing','synthetic']),'Traceable structure evidence class required; synthetic site input prohibited')
        centers=b.get('centers_ft',[])
        need(len(centers)==b.get('count') and all(len(p)==2 and all(finite(v) for v in p) for p in centers),'US/DS centerline pairs required')
        if ui is not None and all(finite(b.get(k)) for k in ['length_ft','distance_us_ft']):
            need(b['length_ft']+b['distance_us_ft']<xs[ui]['reach_lengths_ft'][1],'Culvert exceeds face reach length')
            if finite(b.get('span_ft')):
                for side in [0,1]:
                    ctr=sorted(p[side] for p in centers if len(p)==2 and finite(p[side]))
                    need(all(v-u>=b['span_ft'] for u,v in zip(ctr,ctr[1:])),'Barrel openings overlap')
                    if ctr:
                        sec=xs[ui+side];need(ctr[0]-b['span_ft']/2>=sec['station_ft'][0] and ctr[-1]+b['span_ft']/2<=sec['station_ft'][-1],'Barrel lies outside face section')
        if b.get('shape')=='circular': need(b.get('span_ft')==b.get('rise_ft'),'Circular diameter must equal rise/span')
    # Compare all groups, including lateral crossing between upstream/downstream ends.
    openings=[]
    for b in groups:
        if finite(b.get('span_ft')):
            openings.extend((p[0],p[1],b['span_ft']) for p in b.get('centers_ft',[]) if len(p)==2 and all(finite(v) for v in p))
    for i,a in enumerate(openings):
        for b in openings[i+1:]:
            need((a[0]-b[0])*(a[1]-b[1])>0 and all(abs(a[k]-b[k])>=(a[2]+b[2])/2 for k in [0,1]),'Barrel openings overlap or cross between groups/ends')
    road=s.get('road',{}); aa=road.get('station_ft',[]);zz=road.get('elevation_ft',[])
    need(len(aa)==len(zz) and len(aa)>=2 and all(finite(v) for v in aa+zz),'Road crest profile required')
    if aa: need(all(a<b for a,b in zip(aa,aa[1:])),'Road station order')
    need(road.get('profile_mode','shared') in ['shared','distinct'],'Road profile mode must be shared or distinct')
    if road.get('profile_mode')=='distinct':
        da=road.get('downstream_station_ft') or [];dz=road.get('downstream_elevation_ft') or []
        need(len(da)==len(dz) and len(da)>=2 and all(finite(v) for v in da+dz),'Distinct downstream road profile required')
        if da:need(all(a<b for a,b in zip(da,da[1:])),'Downstream road station order')
    elif road.get('downstream_station_ft') or road.get('downstream_elevation_ft'):
        errors.append('Select distinct road profiles to use downstream values; unused geometry must not be silently discarded')
    for k in ['width_ft','distance_us_ft','weir_coefficient']:
        need(finite(road.get(k)) and road[k]>0,'Road '+k+' required')
    regime=g.get('flow_regime','mixed')
    need(regime in ['subcritical','mixed'],'Select a supported steady flow regime: subcritical or mixed')
    for side in (['downstream'] if regime=='subcritical' else ['upstream','downstream']):
        v=g.get('boundary_slopes',{}).get(side)
        need(finite(v) and v>0,'Positive normal-depth slope required: '+side)
    need(bool(g.get('provenance')),'Geometry provenance required')
    errors.extend(q['code']+' XS '+','.join(map(str,q['sections'])) for q in spatial_issues(xs))
    errors.extend(review_errors(g))
    return errors

def gate(path, c, scenario):
    missing=[]; g=None
    if c.get('section_workflow'):missing.append('Terrain section workflow requires explicit section review and input approval')
    terrain=c.get('terrain',{})
    if terrain.get('mode')=='local':
        for key in ['raster','provenance','vertical_datum']:
            if not isinstance(terrain.get(key),str) or not terrain[key].strip() or terrain[key].lower() in ['unknown','unreviewed']:
                missing.append('Reviewed local terrain '+key+' is required')
        if terrain.get('vertical_unit') not in ['m','US survey foot','international foot']:
            missing.append('Reviewed local terrain vertical_unit is required')
    if c.get('model_proposal_pending'):missing.append('Model configuration proposal is pending explicit conditional approval')
    if c.get('configuration_approval'):
        try:
            receipt=read(safe_path(path.parent,c['configuration_approval']))
            if not (receipt.get('status')=='CONDITIONALLY_AUTHORIZED_NOT_ENGINEERING_ACCEPTED' or receipt.get('status')=='CONDITIONAL_RUN_REQUESTED' and receipt.get('policy')=='local_computation_v1') or not intact(receipt['sources']+receipt['files']) or item(path) not in receipt['files']:
                missing.append('Configuration approval or bound evidence changed')
        except Exception as e:missing.append('Configuration approval: '+str(e))
    if c.get('native_project'):
        if c.get('native_import_review'):
            try:
                receipt=read(safe_path(path.parent,c['native_import_review']))
                if not (receipt.get('status')=='CONDITIONALLY_AUTHORIZED_NOT_ENGINEERING_ACCEPTED' or receipt.get('status')=='CONDITIONAL_RUN_REQUESTED' and receipt.get('policy')=='local_computation_v1') or not intact(receipt['sources']+receipt['files']+[receipt['inspection']]) or item(path) not in receipt['files']:
                    missing.append('Native import review or its bound source/configuration files changed')
            except Exception as e:missing.append('Native import review: '+str(e))
        elif c['case_kind'] not in ['official_benchmark','software_validation']: missing.append('Use workflow.py native-import to inspect and authorize a native site project')
        if not c.get('expected_native'): missing.append('expected_native readback specification required')
        if c.get('benchmark_preparation'):
            try:
                preparation=read(safe_path(path.parent,c['benchmark_preparation']))
                if not intact(preparation['files']+preparation['source_snapshots']):
                    missing.append('Prepared benchmark inputs or source snapshots changed')
            except Exception as e:missing.append('Benchmark preparation record: '+str(e))
    else:
        if not c.get('geometry'): missing.append('Reviewed flowline, complete external XS, banks, reach lengths, culvert dimensions/inverts/floor/inlet, road crest and boundary slopes')
        else:
            try:
                g=read(safe_path(path.parent,c['geometry']));missing.extend(geometry_errors(g,c['case_kind']=='software_validation'))
            except Exception as e:missing.append('Invalid geometry input: '+str(e))
        if not c.get('geometry_review'): missing.append('Recorded geometry review')
        if not c.get('authorization'): missing.append('Site-specific conditional scenario authorization/evidence; no inherited site approval')
        else:
            try:
                auth=read(safe_path(path.parent,c['authorization']))
                if auth.get('project_id')!=c['project_id']:missing.append('Authorization belongs to a different site')
                if not c.get('geometry') or auth.get('allowed_geometry_sha256')!=sha(safe_path(path.parent,c['geometry'])):
                    missing.append('Geometry changed or not covered by recorded authorization')
            except Exception as e:missing.append('Authorization record: '+str(e))
        for key in ['channel_n','overbank_n','culvert_n']:
            if not finite(scenario.get(key)) or not 0<scenario[key]<1: missing.append(key)
        if not scenario.get('parameter_source'): missing.append('Roughness parameter provenance')
    profiles=scenario.get('profiles',[])
    if not profiles: missing.append('Flow profiles')
    for p in profiles:
        if p.get('approved_for_model') is False or p.get('review_status') in ['UNREVIEWED','DRAFT_REQUIRES_REVIEW','CANDIDATE_REQUIRES_REVIEW']:
            missing.append('Unreviewed hydrology candidate cannot be a model profile: '+p.get('id','?'))
        if not finite(p.get('flow_cfs')) or p['flow_cfs']<=0 or not p.get('source'): missing.append('Traceable positive flow_cfs for '+p.get('id','?'))
        if not isinstance(p.get('id'),str) or not p['id'].isascii() or any(x in p['id'] for x in ',\n\r'): missing.append('ASCII profile name without comma/newline')
    if len({p.get('id') for p in profiles})!=len(profiles):missing.append('Duplicate profile names')
    return dict(status='BLOCKED' if missing else 'READY_CONDITIONAL',blocking_items=missing,
        input_adequacy_status='INCOMPLETE' if missing else ('OFFICIAL_BENCHMARK' if c['case_kind']=='official_benchmark' else 'SOFTWARE_VALIDATION_ONLY' if c['case_kind']=='software_validation' else 'CONDITIONAL_UNVERIFIED'),
        engineering_acceptance_status='NOT_ASSESSED'),g
