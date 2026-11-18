"""Public-source attempts, local extraction and reviewable parameter candidates."""
import copy
import hashlib
import json
import re
from pathlib import Path
from .common import ROOT,read,save,item,rel,digest,intact,unique_id,finite,utc
from . import source_extract as extract

def snapshot(m):
    entry=m.get('source_analysis')
    return read(ROOT/entry['path']) if entry and intact([entry]) else {}

def add_file(m,name,raw,url=None):
    from . import app_core as core
    name=Path(name.replace('\\','/')).name
    if not name or len(raw)>15_000_000:raise ValueError('Source file exceeds 15 MB or has no filename')
    fingerprint=hashlib.sha256(raw).hexdigest()
    old=next((f for f in m['attachments'] if f['sha256']==fingerprint and intact([f])),None)
    if old:return old
    p=core.folder(m['id'])/'materials'/unique_id()/name;p.parent.mkdir(parents=True);p.write_bytes(raw)
    entry=dict(**item(p,'source_material'),original_name=name,usage='Source extraction attempted; confirm semantic interpretation',source_url=url)
    m['attachments'].append(entry);return entry

def import_folder(key,body):
    """Read only the explicitly selected local directory; never execute content."""
    from . import app_core as core
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Refresh before importing material')
    root=Path(str(body.get('path',''))).expanduser()
    if not root.is_absolute() or str(root).startswith('\\\\') or not root.is_dir():raise ValueError('Choose a local source-material folder')
    root=root.resolve();files=[];total=0
    for p in root.rglob('*'):
        if p.is_symlink() or not p.is_file() or p.suffix.lower() not in ('.csv','.pdf','.jpg','.jpeg','.png','.txt','.xml','.docx','.kml','.kmz','.tif','.tiff'):continue
        if not p.resolve().is_relative_to(root):continue
        size=p.stat().st_size
        if size>15_000_000:continue
        files.append(p);total+=size
        if len(files)>100 or total>100_000_000:raise ValueError('Select a single site folder (at most 100 files / 100 MB)')
    if not files:raise ValueError('No supported source documents in this folder')
    for p in files:add_file(m,p.name,p.read_bytes())
    m['revision']+=1;core.persist(m,'IMPORT_SOURCE_FOLDER',dict(folder=str(root),count=len(files)))
    return core.launch(key,'analyze')

def progress(m,text):
    from . import app_core as core
    m['phase']=text;core.persist(m)

def discover(m,out):
    from .source_fetch import Download,CATALOG,MA_RELEASE,MA_SURVEY,search_url,survey_members,resolve_public_archive,PublicDownloadRequired
    c=read(ROOT/m['project']);loc=c.get('location');attempts=[];links=[];download=Download()
    if not loc:return [dict(route='public_catalog',status='NEEDS_COORDINATES')],[]
    progress(m,'Searching USGS source catalog / 正在查询 USGS 资料目录')
    url=search_url(loc['latitude'],loc['longitude'])
    try:
        result=download.json(url);save(out/'search.json',result)
        links=[dict(title=r.get('title','USGS record'),url=CATALOG+r['id']) for r in result.get('items',[]) if re.fullmatch('[0-9a-f]{24}',r.get('id',''))]
        attempts.append(dict(route='public_catalog',status='FOUND_RECORDS' if links else 'NO_CATALOG_MATCH',url=url,count=len(links),source=item(out/'search.json'),note='Catalog footprints may cover large regions; links are not a verified site match.'))
    except Exception as e:attempts.append(dict(route='public_catalog',status='NETWORK_FAILED',url=url,error=str(e)))
    from .source_fema import discover as discover_fema
    fema_attempts,fema_links=discover_fema(m,loc,out,download)
    attempts+=fema_attempts;links+=fema_links
    # A verified tabular provider. Other catalog records are not coerced into its schema.
    if not (41<=loc['latitude']<=43 and -74<loc['longitude']<-69):
        attempts.append(dict(route='MA_30_crossing_inventory',status='OUTSIDE_PROVIDER_COVERAGE'));return attempts,links
    try:
        catalog=download.json(CATALOG+MA_RELEASE+'?format=json');save(out/'inventory_catalog.json',catalog)
        entry=next(f for f in catalog['files'] if f['name']=='Stream_Crossing_Model_Site_Information.csv')
        source=add_file(m,entry['name'],download.get(entry['url']),entry['url'])
        matches=extract.site_rows(extract.csv_rows(ROOT/source['path']),loc)
        attempts.append(dict(route='MA_30_crossing_inventory',status='MATCH_CANDIDATE' if matches else 'NO_MATCH_WITHIN_150_M',source=source,matches=matches))
        if len(matches)==1:
            site=matches[0]['row']['MODEL_ID'];progress(m,'Downloading matching survey documents / 下载本站调查资料')
            try:
                catalog=download.json(CATALOG+MA_SURVEY+'?format=json');save(out/'survey_catalog.json',catalog)
                entry=next(f for f in catalog['files'] if f['name']=='Field-Based Hydraulic Model Survey Data.zip')
                # Catalog JSON may advertise an authenticated File Manager page.
                # Its public Attached Files form is a separate anonymous route.
                entry=dict(entry,url=resolve_public_archive(download,MA_SURVEY,entry['name']))
                saved=[]
                for name,raw in survey_members(download,entry,site):
                    saved.append(add_file(m,name,raw,CATALOG+MA_SURVEY+'#'+name));progress(m,'Downloaded '+str(len(saved))+' source files / 已下载资料')
                attempts.append(dict(route='site_survey_download',status='DOWNLOADED',files=saved,bytes=download.used))
            except PublicDownloadRequired as e:attempts.append(dict(route='site_survey_download',status='PUBLIC_DOWNLOAD_ACTION_REQUIRED',reason=e.reason,error=str(e),url=e.page_url,note='Use public Attached Files, not File Manager. Local analysis continues; import the downloaded single-site folder.'))
            except Exception as e:attempts.append(dict(route='site_survey_download',status='DOWNLOAD_FAILED',error=str(e),url=CATALOG+MA_SURVEY,note='Saved documents retained. Import an already downloaded single-site folder, or retry. Full archive download is not attempted.'))
    except Exception as e:attempts.append(dict(route='MA_30_crossing_inventory',status='NETWORK_FAILED',error=str(e)))
    return attempts,links

def analyze(key,network=False,reuse_failed=False):
    from . import app_core as core,intake
    from .app_parameters import objects
    m=core.model(key)
    if not m.get('session') or m.get('native_review') or m.get('active_project'):
        m.update(status='INPUTS_READY',phase='SOURCE_ANALYSIS_NOT_APPLICABLE');core.persist(m);return
    out=core.folder(key)/'source_analysis'/unique_id();out.mkdir(parents=True)
    old=snapshot(m);attempts=old.get('attempts',[]);links=old.get('links',[])
    if network:attempts,links=discover(m,out)
    # Persist successful downloads before parsing; a bad document cannot erase them.
    core.persist(m)
    sp,p,d,c,g=objects(m);allowed={f['key']:f for f in intake.fields(c,g,m['scenario'])}
    scenario_index=next(i for i,scenario in enumerate(c['scenarios']) if scenario['id']==m['scenario'])
    profile_index=next((i for i,profile in enumerate(c['scenarios'][scenario_index]['profiles'])
                        if profile['id'].lower()=='q100'),None)
    flow_field=f'c.scenarios.{scenario_index}.profiles.{profile_index}.flow_cfs' if profile_index is not None else None
    candidates=[];documents=[];surveys=[];matches=[];cache={x['source']['sha256']:x for x in old.get('documents',[])}
    runtime=extract.runtime_signature()
    for candidate0 in old.get('candidates',[]):
        if candidate0.get('identified_points') and intact([candidate0['source']]) and candidate0.get('survey_settings_hash')==digest(m.get('survey_settings',{})):candidates.append(candidate0)
    def candidate(field,value,basis,source,classification='reported',auto=False,**extra):
        if field not in allowed or value in (None,'',[]):return
        record=dict(field=field,value=value,basis=basis,evidence_class=classification,source=source,auto_eligible=auto,**extra)
        record['candidate']=digest(record);record['condition']=dict(en=basis,zh='资料提取候选：'+basis)
        candidates.append(record)
    for i,entry in enumerate(m['attachments']):
        progress(m,f'Inspecting material {i+1}/{len(m["attachments"])} / 解析资料：'+entry['original_name'])
        if not intact([entry]):
            documents.append(dict(source=entry,status='SOURCE_CHANGED',warnings=['File missing or changed; reimport the current source']));continue
        path=ROOT/entry['path'];doc=dict(source=entry,status='INSPECTED',warnings=[])
        try:
            if path.suffix.lower()=='.csv':
                rows=extract.csv_rows(path)
                if rows and {'field','value'}<=set(rows[0]):
                    params,errors=extract.parameter_rows(rows,allowed);doc.update(method='Explicit parameter table',warnings=errors)
                    for v in params:
                        field=v['field'];basis=v['basis']+f'; CSV row {v["row"]}; source units explicitly matched.'
                        if 'invert' in field or 'elevation_ft' in field:
                            if not v.get('datum') or v['datum']!=g.get('vertical_datum'):
                                doc['warnings'].append(dict(row=v['row'],error='Elevation datum missing or does not match the model; not proposed'));continue
                        candidate(field,v['value'],basis,entry,v['evidence_class'],datum=v.get('datum'))
                elif rows and {'LAT','LONG','MODEL_ID','PK1AEP'}<=set(rows[0]):
                    found=extract.site_rows(rows,c.get('location'));matches+=found;doc.update(method='USGS site inventory',matches=found)
                    if len(found)==1:
                        match=found[0];r=match['row'];basis=f'USGS site inventory row {match["row_number"]}, MODEL_ID {r["MODEL_ID"]}, {match["distance_m"]} m from selected location. Confirm crossing and applicability. Source survey/assessment dates may differ.'
                        candidate(flow_field,extract.numeric(r.get('PK1AEP')),basis+' PK1AEP is regional-regression 1% AEP flow in cfs, not an observed discharge.',entry,auto=match['distance_m']<=25)
                        for name,col in [('span_ft','INLET_SPAN'),('rise_ft','INLET_HEIGHT'),('length_ft','CULVERT_LENGTH')]:
                            candidate('g.structure.groups.0.'+name,extract.numeric(r.get(col)),basis+' Inventory main opening only; does not describe every auxiliary pipe.',entry)
                        shape={'box':'box','pipe':'circular','circular':'circular'}.get(str(r.get('EXIST_STRUCTURE','')).lower())
                        if shape:candidate('g.structure.groups.0.shape',shape,basis+' Main opening only.',entry)
                else:
                    spec=extract.survey(rows,m.get('survey_settings',{}).get(entry['sha256'],{}).get('columns'))
                    doc.update(method='Survey / table column inference',headers=list(rows[0]) if rows else [])
                    if spec:surveys.append(dict(source=entry,**spec))
            else:
                cached=cache.get(entry['sha256'])
                if extract.reuse_document(cached,reuse_failed,runtime):
                    doc=copy.deepcopy(cached)
                    doc.update(source=entry,cache_reused=True)
                    doc.setdefault('extraction_runtime',None)
                else:
                    doc.update(extraction_runtime=runtime)
                    doc.update(extract.document_text(path,out/('extract_'+str(i))))
                doc['extractor_version']=extract.EXTRACTOR_VERSION
                from .source_tables import candidates as table_candidates
                for value in table_candidates(doc.get('tables',[]),scenario_index,profile_index):
                    candidate(value['field'],value['value'],value['basis'],entry,value['evidence_class'],
                              **{key:record for key,record in value.items() if key not in ('field','value','basis','evidence_class')})
                for flow in extract.text_flows(doc.get('text','')):
                    candidate(flow_field,flow['value'],'Unverified document match: '+flow['excerpt']+'. Confirm the location, event and text against the original.',entry,'inferred' if 'OCR' in doc.get('method','') else 'reported')
                for v in extract.text_parameters(doc.get('text',''),allowed):
                    origin='assumed' if v.get('evidence_class')=='assumed' else 'inferred' if 'OCR' in doc.get('method','') else 'reported'
                    candidate(v['field'],v['value'],'Unverified labelled text: '+v['excerpt']+'. Confirm site, group and units against the original.',entry,origin,datum=v.get('datum'))
        except Exception as e:doc.update(status='EXTRACTION_FAILED',error=str(e),extractor_version=extract.EXTRACTOR_VERSION)
        doc.setdefault('extraction_runtime',runtime)
        documents.append(doc)
    for s in surveys:
        context=extract.control_context(documents,s['points'])
        settings=m.get('survey_settings',{}).get(s['source']['sha256'],{})
        s['context_candidate']=context;s['context']=settings if settings.get('horizontal_crs') else context
        if not s['context']:s['status']='CRS_AND_UNITS_REQUIRED'
        elif context:
            candidate('g.vertical_datum',context['vertical_datum'],context['basis'],s['source'])
    filled=[]
    # Only unambiguous close-site flow candidates may fill an empty field. Existing
    # values, all structure dimensions and all assumptions require an explicit choice.
    for field in allowed:
        choices=[v for v in candidates if v['field']==field]
        same=choices and all(v['value']==choices[0]['value'] for v in choices)
        if same and any(v['auto_eligible'] for v in choices) and allowed[field]['value'] in (None,'',[]):
            choice=next(v for v in choices if v['auto_eligible'])
            d['answers'][field]=dict(value=choice['value'],evidence_class='reported',basis=choice['basis'],confirmed=False,candidate_record=choice)
            if field.endswith('.flow_cfs'):d['answers'][field[:-8]+'source']=dict(value=choice['basis'],evidence_class='reported',basis=choice['source']['path'],confirmed=False)
            filled.append(field)
    if filled:intake.save_draft(sp,d)
    source_records=list(m['attachments'])
    for attempt in attempts:
        source_records+=attempt.get('sources',[])
        if attempt.get('source'):source_records.append(attempt['source'])
    result=dict(schema='source_acquisition_1',created_utc=utc(),attempts=attempts,links=links,documents=documents,surveys=surveys,candidates=candidates,matches=matches,auto_filled=filled,
        scope='Public USGS catalog, MA crossing inventory and coordinate-based effective FEMA FIS discovery. Local parameter/survey CSV, PDF text/layout tables and Windows OCR. Site applicability remains reviewable.',
        sources=list({source['path']:source for source in source_records}.values()))
    save(out/'analysis.json',result)
    m.update(source_analysis=item(out/'analysis.json','source_extraction'),revision=m['revision']+1,status='INPUTS_READY',phase='REVIEW_SOURCE_CANDIDATES',errors=[])
    core.persist(m,'SOURCE_ANALYSIS',dict(analysis=m['source_analysis'],auto_filled=filled))

def configure_survey(key,body):
    from . import app_core as core
    from pyproj import CRS
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Refresh before changing survey interpretation')
    source=next((f for f in m['attachments'] if f['sha256']==body.get('source')),None)
    if not source:raise ValueError('Unknown survey source')
    settings=body['settings'];crs=CRS.from_user_input(settings['horizontal_crs'])
    if not crs.is_projected:raise ValueError('Survey requires a projected CRS with linear units')
    if settings['vertical_unit'] not in ('m','US survey foot','international foot') or not str(settings['vertical_datum']).strip():raise ValueError('Choose survey elevation unit and datum')
    columns=settings.get('columns',{})
    if set(columns)-{'id','x','y','z','code'}:raise ValueError('Unknown survey column')
    m.setdefault('survey_settings',{})[source['sha256']]=dict(horizontal_crs=crs.to_string(),vertical_unit=settings['vertical_unit'],vertical_datum=str(settings['vertical_datum']).strip(),columns=columns,basis='User-confirmed survey CRS, vertical unit and column interpretation')
    m['revision']+=1;core.persist(m,'SURVEY_CONTEXT');return core.launch(key,'analyze')

def route_for(field):
    key=field['key']
    if '.flow_cfs' in key:return ('USGS inventory / effective FEMA FIS → location-labelled Q100 table or text → parameter CSV','USGS 站点表／有效 FEMA FIS → 带地点的 Q100 表格或文本 → 参数 CSV','Confirm drainage location and 1% AEP applicability; flow is not derived from DEM.','核对汇水地点及 1% AEP 适用性；DEM 不能确定设计流量。')
    if 'invert' in key:return ('Survey XYZ + datum → identify invert points → labelled parameter CSV → conditional map estimate','测量 XYZ＋基准 → 指认涵底测点 → 明确参数表 → 条件性地图估计','Crown/bed codes alone do not prove a buried invert. Select the actual point or retain an explicit assumption.','仅有管顶／河床代码不能证明埋藏涵底。需指认真实点或采用明确假设。')
    if any(s in key for s in ('_n','.mann','bottom_n_depth')):return ('Parameter CSV / source text → official roughness references','参数表／原文 → 官方糙率参考','Match material, vegetation and depth; photographs alone do not uniquely determine n.','匹配材质、植被和水深；照片不能唯一确定糙率。')
    if key.startswith('g.cross_sections.') or 'boundary_slopes' in key:return ('Survey points / DEM → section, bank and slope candidates → parameter CSV','测点／DEM → 断面、左右岸及坡度候选 → 参数表','Select exterior flow direction first, then generate terrain candidates and inspect uncertainty.','先确认外部流向，再生成地形候选并检查不确定项。')
    if '.road.' in key:return ('Survey RDCL / crest points → mapped crest DEM sampling → parameter CSV','路面／高点测点 → 地图高点线 DEM 采样 → 参数表','Road centerline need not be the overtopping crest; identify coverage and upstream/downstream faces.','道路中心线未必是越流高点，需辨认覆盖范围与进出口。')
    if '.groups.' in key:return ('Inventory → survey/photo OCR → identified points / dimensions → parameter CSV','站点表 → 测量／照片 OCR → 已辨认测点／尺寸 → 参数表','Inventory may describe only the main opening. Confirm group, interior/exterior dimensions and construction.','站点表可能仅描述主孔，需确认涵孔组、内外尺寸和构造。')
    if any(s in key for s in ('crs','datum')):return ('DEM metadata → OPUS survey control check → explicit coordinate interpretation','DEM 元数据 → OPUS 测量控制复核 → 明确坐标解释','No automatic vertical datum shift is applied.','不自动执行高程基准转换。')
    return ('Explicit parameter CSV → source text → geometry-derived / engineering-setting candidates','明确参数 CSV → 资料原文 → 几何推导／工程设置候选','Model conventions and hydraulic regime still require applicability confirmation.','模型约定及流态仍须确认适用性。')

def fis_scope(candidate):
    """Only comparable, labelled rows of the same report table can be set aside."""
    if not candidate.get('requires_applicability_review'):
        return None
    locus = candidate.get('source_locus') or {}
    context = candidate.get('hydrologic_context') or {}
    source_hash = (candidate.get('source') or {}).get('sha256')
    stream = context.get('stream')
    if not source_hash or not locus.get('table_number') or not isinstance(stream, str) or not stream.strip() or stream != locus.get('stream'):
        return None
    location = None
    table = (locus.get('table_title') or '').casefold()
    if table == 'summary of discharges':
        location = context.get('location')
        if not isinstance(location, str) or not location.strip() or location != locus.get('location') or context.get('aep_percent') != 1:
            return None
    elif table != 'roughness coefficients':
        return None
    river_key = ' '.join(stream.casefold().split())
    location_key = ' '.join(location.casefold().split()) if location else None
    return (source_hash, locus['table_number'], table), (river_key, location_key)


def selected_fis_review(field, choices, selected_streams):
    answer = field.get('answer') or {}
    prior = answer.get('candidate_record') or {}
    scope = fis_scope(prior)
    if not scope or answer.get('automatic_preparation') or prior.get('auto_eligible'):
        return None
    if prior not in choices or field['value'] != prior['value'] or any(
        answer.get(key) != prior.get(key) for key in ('value', 'evidence_class', 'basis')
    ):
        return 'FIS_SELECTION_CHANGED'
    table, place = scope
    if table[2] == 'roughness coefficients' and selected_streams - {place[0]}:
        return 'FIS_STREAM_MISMATCH'
    for candidate in choices:
        other = fis_scope(candidate)
        if other and other[0] == table and other[1] != place:
            continue
        if any(candidate.get(key) != prior.get(key) for key in ('value', 'range', 'evidence_class')):
            return 'CONFLICT'
    return 'FIS_ROW_SELECTED'


def enrich(m,fields):
    a=snapshot(m);candidates=a.get('candidates',[]);sources_ok=not a.get('sources') or intact(a['sources'])
    datum=next((f['value'] for f in fields if f['key']=='g.vertical_datum'),None)
    streams_by_scenario = {}
    for field in fields:
        saved = (field.get('answer') or {}).get('candidate_record') or {}
        scope = fis_scope(saved)
        if scope and scope[0][2] == 'summary of discharges' and saved in candidates and field['value'] == saved['value']:
            scenario = field['key'].partition('.profiles.')[0]
            streams_by_scenario.setdefault(scenario, set()).add(scope[1][0])
    for f in fields:
        choices=[v for v in candidates if v['field']==f['key'] and (not v.get('datum') or v['datum']==datum)] if sources_ok else []
        f['parameter_candidates']+=choices
        different=[v for v in choices if not f['missing'] and v['value']!=f['value']]
        multi=choices and any(v['value']!=choices[0]['value'] for v in choices)
        scenario = f['key'].rsplit('.', 1)[0]
        fis_status = selected_fis_review(f, choices, streams_by_scenario.get(scenario, set()))
        f['source_conflict'] = fis_status != 'FIS_ROW_SELECTED' if fis_status else bool(different or multi)
        en,zh,next_en,next_zh=route_for(f)
        tried=[dict(route=v['route'],status=v['status']) for v in a.get('attempts',[])]
        if a:tried.append(dict(route='local_document_extraction',status='PARTIAL_FAILURE' if any(d.get('status')=='EXTRACTION_FAILED' for d in a.get('documents',[])) else 'INSPECTED' if a.get('documents') else 'NO_DOCUMENTS',count=len(a.get('documents',[])),failed=sum(d.get('status')=='EXTRACTION_FAILED' for d in a.get('documents',[])),scope='Shared source discovery; not a separate Internet search for this field'))
        if f.get('parameter_candidates'):tried.append(dict(route='parameter_candidate_evaluation',status='CANDIDATE',count=len(f['parameter_candidates'])))
        if not sources_ok:
            status = 'SOURCE_CHANGED'
        elif fis_status:
            status = fis_status
        elif f['source_conflict']:
            status = 'CONFLICT'
        elif choices:
            status = 'CANDIDATE'
        else:
            status = 'NO_EXTRACTED_VALUE' if a else 'NOT_ATTEMPTED'
        f['acquisition']=dict(route=dict(en=en,zh=zh),next=dict(en=next_en,zh=next_zh),status=status,attempted=bool(a),attempts=tried,field_value_extracted=bool(choices),candidate_sources=[v.get('source') for v in choices],automatic_methods_evaluated=['explicit_source_values','terrain_or_geometry_proposals'],manual_decision_required=f['missing'] or f['source_conflict'])
    return fields

def overlay(m,map_data):
    from pyproj import Transformer,CRS
    a=snapshot(m);result=[];issues=[]
    for survey in a.get('surveys',[]):
        context=survey.get('context')
        if not context or not intact([survey['source']]):continue
        try:
            transform=Transformer.from_crs(context['horizontal_crs'],map_data['crs'],always_xy=True)
            for p in survey['points'][:5000]:
                x,y=transform.transform(p['x'],p['y'])
                if not finite(x) or not finite(y):continue
                result.append(dict(**p,xy=[x,y],source=survey['source']['sha256'],unit=context['vertical_unit'],datum=context['vertical_datum'],context_basis=context['basis']))
        except Exception as e:issues.append(str(e))
    from .app_parameters import objects
    from .app_automation import resolve
    mapped,errors=resolve(m,objects(m)[4])
    openings=[dict(group=r['group'],barrel=r['barrel'],xy=[e['xy'] for e in r['ends']],interpretation=r['interpretation']) for r in mapped]
    return dict(**map_data,survey_points=result,survey_issues=issues,opening_items=openings)

def select_points(key,body):
    """Turn explicitly identified survey points into conservative model candidates."""
    from . import app_core as core
    from .app_parameters import objects
    from pyproj import CRS
    m=core.model(key);core.require_idle(m)
    if body.get('revision')!=m['revision']:raise ValueError('Refresh before identifying survey points')
    a=snapshot(m);survey=next((s for s in a.get('surveys',[]) if s['source']['sha256']==body.get('source')),None)
    if not survey or not survey.get('context') or not intact([survey['source']]):raise ValueError('Survey coordinates/units or source are unresolved')
    context=survey['context'];ids=body.get('points',[])
    points=[next((p for p in survey['points'] if p['id']==str(i)),None) for i in ids]
    if not points or len(points)>100 or any(p is None for p in points) or len(ids)!=len(set(ids)):raise ValueError('Choose unique existing survey point IDs')
    sp,p,d,c,g=objects(m);field=body.get('field','');allowed={f['key']:f for f in __import__(__package__+'.intake',fromlist=['fields']).fields(c,g,m['scenario'])}
    if field not in allowed:raise ValueError('Unknown target field')
    factor={'m':1/.3048,'US survey foot':(1200/3937)/.3048,'international foot':1}[context['vertical_unit']]
    if field.endswith(('.us_invert_ft','.ds_invert_ft')):
        if len(points)!=1 or context['vertical_datum']!=g.get('vertical_datum'):raise ValueError('Invert requires one identified point and a matching model elevation datum')
        value=round(points[0]['z']*factor,6);basis='User identified this surveyed point as the interior invert. No crown-to-invert or datum shift applied.';classification='reported'
    elif field.endswith(('.length_ft','.span_ft','.width_ft')):
        if len(points)!=2:raise ValueError('Dimension requires exactly two endpoint points')
        import math
        factor=CRS.from_user_input(context['horizontal_crs']).axis_info[0].unit_conversion_factor/.3048
        value=round(math.hypot(points[1]['x']-points[0]['x'],points[1]['y']-points[0]['y'])*factor,6)
        basis='Plan distance between user-identified endpoints; conditional proxy for the selected interior dimension. Check skew, walls and feature identity.';classification='inferred'
    else:raise ValueError('Point identification supports invert elevations and length/span/road width only')
    record=dict(field=field,value=value,evidence_class=classification,basis=basis+' Points '+', '.join(map(str,ids))+'; '+context['basis'],source=survey['source'],auto_eligible=False,identified_points=points,survey_settings_hash=digest(m.get('survey_settings',{})))
    if field.endswith(('.us_invert_ft','.ds_invert_ft')):record['datum']=context['vertical_datum']
    record['candidate']=digest(record);record['condition']=dict(en=record['basis'],zh='已指认测点的计算候选：'+record['basis'])
    a['candidates'].append(record);out=core.folder(key)/'source_analysis'/unique_id()/'analysis.json';save(out,a)
    m.update(source_analysis=item(out,'source_extraction'),revision=m['revision']+1);core.persist(m,'IDENTIFY_SURVEY_POINTS',dict(field=field,points=ids))
    return core.view(key)
