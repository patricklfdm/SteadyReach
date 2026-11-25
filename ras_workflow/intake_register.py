"""Edition-bound inventory of hydraulic evidence. Unknown metadata stays unknown."""
from pathlib import Path

from .common import ROOT, item, read, safe_path

CATEGORIES=('terrain','channel','flow','stage','structure')
REQUESTS={
 'terrain':('Obtain the clipped elevation raster, vertical reference and coverage.','索取河段高程栅格、垂直基准和覆盖范围。'),
 'channel':('Request dated submerged channel sections tied to the project datum.','索取注明测量日期、统一基准的水下断面。'),
 'flow':('Obtain the event discharge or published frequency table for this reach.','索取本站事件流量或标明河段的频率表。'),
 'stage':('Obtain the water elevation for the modeled event at the boundary, with datum and uncertainty.','索取模型边界在同一事件的水位、基准和测量不确定度。'),
 'structure':('Request inlet and outlet invert levels, barrel length and roadway survey for each group.','向测量方索取每组涵孔的进出口涵底、涵长和道路实测剖面。')}


def refs(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str) and len(value['sha256'])==64:
            yield {k:value[k] for k in ('path','sha256','size_bytes','role','source','url','original_name') if k in value}
        else:
            for v in value.values():yield from refs(v)
    elif isinstance(value,list):
        for v in value:yield from refs(v)


def field_kind(key):
    if key.endswith('.flow_cfs'):return 'flow'
    if key.startswith('g.structure.'):return 'structure'
    if key.startswith(('g.boundaries.','g.boundary_slopes.')):return 'stage'
    if key=='g.channel_geometry_basis':return 'channel'
    if key.startswith('c.terrain.'):return 'terrain'


def field_record(f):
    answer=f.get('answer') or {};candidate=answer.get('candidate_record') or {}
    choices=[dict(value=c.get('value'),basis=c.get('basis'),classification=c.get('evidence_class'),sources=list(refs(c)))
             for c in f.get('parameter_candidates',[])]
    return dict(key=f['key'],label=f.get('label'),value=f.get('value'),unit=f.get('unit'),required=f.get('required',True),classification=f.get('evidence_class'),
                basis=f.get('basis'),missing=bool(f.get('missing')),sources=list(refs(candidate)),candidates=choices)


def context(m,prepared=None):
    from .common import intact
    from .app_parameters import objects,rows
    from .app_acquisition import snapshot
    fields=[];config={};geom={};extra=[]
    sealed=m.get('pending_review') if m.get('active_project') else None
    if prepared is not None:
        config,geom,all_fields=prepared
        fields=[field_record(f) for f in all_fields if field_kind(f['key'])]
        extra=[config.get('field_return_sources',[]),config.get('returned_observations',[]),config.get('returned_observation_originals',[])]
    elif sealed and intact([sealed]) and not m.get('native_review'):
        packet=read(safe_path(ROOT,sealed['path']));inputs=packet['inputs']
        config=inputs['configuration'];geom=inputs['geometry']
        fields=[field_record(f) for f in packet['fields'] if field_kind(f['key'])]
        extra=[config.get('field_return_sources',[]),config.get('returned_observations',[]),config.get('returned_observation_originals',[])]
    elif m.get('session') and not m.get('native_review'):
        obj=objects(m);_,_,draft,config,geom=obj
        fields=[field_record(f) for f in rows(m,context=obj) if field_kind(f['key'])]
        extra=[draft.get('uploads',[]),config.get('field_return_sources',[]),config.get('returned_observations',[]),config.get('returned_observation_originals',[])]
    elif m.get('project'):
        config=read(safe_path(ROOT,m['project']))
    if m.get('source_analysis') and not intact([m['source_analysis']]):raise ValueError('Restore the registered source analysis or replay the frozen intake / 请找回来源分析原件或重放冻结资料')
    acq=snapshot(m);terrain=m.get('terrain') or {}
    scenario=next((s for s in config.get('scenarios',[]) if s.get('id')==m.get('scenario')), {})
    # Retain the working raster and catalog metadata. Original unclipped tiles are identified separately.
    products=[{k:v for k,v in row.items() if k not in ('source','metadata')} for row in terrain.get('products',[])]
    tiles=[row['source'] for row in terrain.get('products',[]) if isinstance(row.get('source'),dict)]
    sources=[m.get('attachments',[]),m.get('input_choices',[]),m.get('source_analysis'),m.get('terrain',{}).get('raster'),
             terrain.get('metadata'),[r.get('metadata') for r in terrain.get('products',[])],acq.get('attempts',[]),fields,extra]
    imagery={};delivery=config.get('delivery') or {};raster=(delivery.get('imagery') or {}).get('raster')
    if raster and m.get('project'):
        base=safe_path(ROOT,m['project']).parent;path=safe_path(base,raster)
        if path.is_file():
            imagery['raster']=item(path,'intake_imagery')
            for name in delivery.get('additional_sources',[]):
                receipt=safe_path(base,name)
                if receipt.suffix.lower()=='.json' and receipt.is_file():
                    record=read(receipt)
                    if isinstance(record,dict) and record.get('schema_version')=='naip_acquisition_1.0' and (record.get('raster') or {}).get('sha256')==imagery['raster']['sha256']:
                        imagery['receipt']=item(receipt,'intake_imagery_receipt');break
    notes=m.get('intake_source_notes',[]);sources.extend((imagery,notes));members={r['path']:r for r in refs(sources)}
    return dict(schema='hydraulic_intake_v1',edition=m['id'],route=m.get('route'),model_type=m.get('model_type'),
       location=config.get('location',{}),profiles=scenario.get('profiles',[]),geom={k:geom.get(k) for k in
       ('horizontal_crs','vertical_datum','channel_geometry_basis','boundaries','cross_sections','flow_regime')},
       fields=fields,terrain={k:terrain.get(k) for k in ('bbox','vertical_datum','vertical_unit','raster','metadata')},products=products,
       original_tiles=tiles,imagery=imagery,notes=notes,attempts=acq.get('attempts',[]),sources=list(members.values()),
       attachments=[dict(r) for r in refs([m.get('attachments',[]),extra])],source_analysis=m.get('source_analysis'))


def outcome(attempt):
    s=attempt.get('status','')
    if 'CONFLICT' in s:return 'CONFLICT'
    if s=='PARTIAL':return 'PARTIAL'
    if s in ('OUTSIDE_PROVIDER_COVERAGE','NOT_APPLICABLE'):return 'OUTSIDE_COVERAGE'
    if s.startswith(('NO_','NOT_FOUND','EMPTY')):return 'EMPTY'
    if any(k in s for k in ('FAIL','UNAVAILABLE','REQUIRED','ERROR','BLOCKED')):return 'UNAVAILABLE'
    if s in ('FOUND_RECORDS','CANDIDATES','MATCH_CANDIDATE','DOWNLOADED','SUCCESS','READY'):return 'FOUND'
    return 'UNCLASSIFIED'


def inventory(ctx,open_source):
    geom=ctx['geom'];terrain=ctx['terrain'];attached=ctx['attachments'];manifest=None
    survey=next((r for r in attached if r.get('role')=='survey_manifest'),None)
    if survey:manifest=read(open_source(survey))
    from .intake_boundary import documents,screen
    docs=documents(ctx,open_source);boundary=screen(ctx,docs)
    records=[]
    for category in CATEGORIES:
        fields=[f for f in ctx['fields'] if field_kind(f['key'])==category]
        entries=[r for f in fields for r in f['sources']];meta=[]
        status='MISSING';coverage=None;unit=None;datum=None
        if category=='terrain':
            if terrain.get('raster'):entries.append(terrain['raster']);status='AVAILABLE'
            coverage=terrain.get('bbox');datum=terrain.get('vertical_datum');unit=terrain.get('vertical_unit')
            products=ctx['products'];provenance=terrain.get('metadata')
            if provenance:
                entries.append(provenance)
                if Path(provenance['path']).suffix.lower()=='.json':
                    raw=read(open_source(provenance))
                    if isinstance(raw,dict) and (raw.get('raster') or {}).get('sha256')==(terrain.get('raster') or {}).get('sha256'):
                        products=products or raw.get('products',[])
                        coverage=coverage or raw.get('bbox')
            for product in products:
                meta.append({k:product.get(k) for k in ('product_id','title','url','publication_date','last_updated','bounds','source_crs')})
            if status=='AVAILABLE' and any(str(v or '').upper() in ('','UNKNOWN','UNREVIEWED','UNSPECIFIED') for v in (datum,unit)):
                status='CHECK_SOURCE'
            if terrain.get('raster') and not coverage:
                import rasterio
                from rasterio.warp import transform_bounds
                with rasterio.open(open_source(terrain['raster'])) as raster:
                    if raster.crs:coverage=list(transform_bounds(raster.crs,'EPSG:4326',*raster.bounds))
        elif category=='channel':
            basis=geom.get('channel_geometry_basis');datum=geom.get('vertical_datum');unit='ft'
            sections=geom.get('cross_sections') or [];coverage=[s['rs'] for s in sections]
            status='DOCUMENTED_BASIS' if survey and basis in ('combined_survey_and_dem','surveyed_channel') else 'ASSUMED' if sections else 'MISSING'
            if survey:entries.append(survey)
            if basis:meta.append(dict(channel_geometry_basis=basis))
        elif category=='flow':
            unit='cfs';coverage=ctx['location'];meta=list(ctx['profiles'])
            if survey:entries.append(survey)
        elif category=='stage':
            unit='ft';datum=geom.get('vertical_datum');meta=[geom.get('boundaries') or {}]
        elif category=='structure' and ctx['model_type']=='river':status='NOT_APPLICABLE'
        if category=='structure':
            datum=geom.get('vertical_datum');unit='field_specific';coverage=ctx.get('location')
            entries.extend(r for r in attached if r.get('role') in ('source_material','field_original','field_worksheet'))
        if fields and category in ('flow','structure','stage') and status!='NOT_APPLICABLE':
            status=('MISSING' if any(f['missing'] and f['required'] for f in fields) else 'ASSUMED' if any(f['classification'] in ('inferred','assumed','terrain_derived') for f in fields)
                    else 'SOURCE_RECORDED' if entries else 'CHECK_SOURCE')
        if category=='structure' and not fields and status=='MISSING':meta=[dict(site=ctx['location'])]
        dates=[]
        if category=='stage':coverage={'downstream_rs':boundary['end_rs']}
        required_records=[f['key'] for f in fields if (f['missing'] and f['required']) or
                          (f['classification'] in ('inferred','assumed','terrain_derived') and f['key'].endswith(('invert_ft','length_ft','stages_ft','flow_cfs')))]
        if category in ('stage','flow'):
            measured=[m for m in docs['measurements'] if m['kind']==('Discharge' if category=='flow' else 'MeanGageHeight')]
            for m in measured:
                entries.append(m['source']);dates.append(m['date']);meta.append({k:v for k,v in m.items() if k!='source'})
        if category=='stage':
            entries.extend(r['source'] for r in boundary['rows']);dates.extend(r['date'] for r in boundary['rows'])
        for declaration in docs['metadata']:
            if declaration['category']==category:
                entries.append(declaration['source']);dates.append(declaration.get('date'));meta.append(declaration)
        from .river_observations import datum as normalize_datum
        declared={normalize_datum(str(d['datum'])) for d in docs['metadata'] if d['category']==category and d.get('datum')}
        conflicts=sorted(declared-{normalize_datum(str(datum))}) if datum else sorted(declared) if len(declared)>1 else []
        if conflicts and status!='NOT_APPLICABLE':status='CONFLICT'
        records.append(dict(category=category,status=status,coverage=coverage,unit=unit,datum=datum,metadata=meta,conflicting_datums=conflicts,
                 dates=sorted(set(filter(None,dates))),sources=list({r['path']:r for r in entries}.values()),fields=fields,
                 request=REQUESTS[category],requested_fields=required_records))
    return dict(edition=ctx['edition'],records=records,boundary=boundary,sources=ctx['sources'],original_tiles=ctx['original_tiles'],
                searches=[dict(route=a.get('route'),status=a.get('status'),outcome=outcome(a),url=a.get('url'),
                               error=a.get('error'),failures=a.get('failures')) for a in ctx['attempts']])
