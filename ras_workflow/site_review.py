"""Offline, source-bound site intake and map review. No implicit model approval."""
import base64
import copy
import io
import json
import html
import os
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer

from .common import ROOT, finite, intact, item, read, rel, safe_path, save, utc
from .inputs import load, gate
from .source_review import verified_candidates, rows
from .sections import intersect


def render_html(packet, spec):
    template=(ROOT/'ras_workflow/templates/site_review.html').read_text(encoding='utf-8')
    state=(ROOT/'ras_workflow/templates/review_state.js').read_text(encoding='utf-8')
    data=json.dumps(dict(packet=packet,spec=spec),ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return template.replace('__REVIEW_STATE__',state).replace('__REVIEW_DATA__',data)


def register_view(project_id, page, packet_path):
    """Keep one generated local entry; immutable packets remain unchanged."""
    index=ROOT/'status/review_index.json'
    record=read(index) if index.exists() else dict(schema_version='1.0',projects={})
    record['projects'][project_id]=dict(page=item(page),packet=item(packet_path),updated_utc=utc())
    save(index,record)
    return write_index()


def write_index():
    from urllib.parse import quote
    index=ROOT/'status/review_index.json'
    record=read(index) if index.exists() else dict(projects={})
    entries=[]
    for name,r in sorted(record['projects'].items()):
        valid=intact([r['page'],r['packet']])
        link='<a href="'+quote(r['page']['path'])+'">'+html.escape(name)+'</a>' if valid else html.escape(name)+' — changed/missing / 已改变或缺失'
        entries.append('<li>'+link+' <small>'+html.escape(r['updated_utc'])+'</small></li>')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Review workspaces</title>
<style>body{font:17px Segoe UI,Arial;max-width:900px;margin:40px auto;padding:20px;color:#183340}li{margin:20px 0}a{color:#17617b}small{display:block;color:#52666e}button{padding:8px}</style>
<button onclick="const cn=document.documentElement.lang==='en';document.documentElement.lang=cn?'zh-CN':'en';document.getElementById('en').hidden=cn;document.getElementById('cn').hidden=!cn;this.textContent=cn?'English':'简体中文'">简体中文</button>
<div id="en"><h1>Latest review workspaces</h1><p>Choose a project. Drafts and decisions belong to their exact review packet. Export JSON before moving to another computer.</p></div>
<div id="cn" hidden><h1>最新审核工作区</h1><p>选择项目。草稿与决定绑定具体审核包；换电脑前请导出 JSON。</p></div><ul>'''+''.join(entries)+'</ul></html>'
    (ROOT/'REVIEW.html').write_text(page,encoding='utf-8')
    return ROOT/'REVIEW.html'


def refresh_view(packet_path, output):
    pp=safe_path(ROOT,packet_path);p=read(pp);manifest=read(pp.parent/'manifest.json')
    if not intact(manifest['files']+manifest['sources']):raise ValueError('Original review packet or sources changed')
    spec=read(pp.parent/'decisions.template.json')
    if spec['packet']!=item(pp):raise ValueError('Review specification does not match packet')
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    (folder/'index.html').write_text(render_html(p,spec),encoding='utf-8')
    save(folder/'manifest.json',dict(files=[item(folder/'index.html')],sources=[item(pp),item(pp.parent/'manifest.json')],
        created_utc=utc(),kind='presentation_refresh_same_packet',original_decisions_compatible=True))
    register_view(p['project_id'],folder/'index.html',pp)
    return folder/'index.html'


def map_data(project_path, config, geometry, pour_point=None):
    features=[]; crs=None
    if geometry:
        crs=CRS.from_user_input(geometry['horizontal_crs'])
        if not crs.is_projected:raise ValueError('Review geometry requires a projected horizontal CRS')
        for i,line in enumerate(geometry.get('flowlines',[])):
            features.append(dict(id=f'flowline:{i}',kind='flowline',label=line['id'],xy=line['xy'],data=line))
        for i,s in enumerate(geometry['cross_sections']):
            features.append(dict(id=f'section:{i}',kind='section',label='XS '+str(i),xy=s['cutline_xy'],data=s))
    loc=config.get('location')
    if loc:
        if crs is None:
            # A local projected viewing CRS; never relabels a source DEM.
            crs=CRS.from_proj4(f'+proj=aeqd +lat_0={loc["latitude"]} +lon_0={loc["longitude"]} +datum=WGS84 +units=m')
        xy=Transformer.from_crs(4326,crs,always_xy=True).transform(loc['longitude'],loc['latitude'])
        features.append(dict(id='crossing',kind='crossing',label='Location marker / 待核对位置',xy=[list(xy)],data=loc))
    if pour_point and crs:
        xy=Transformer.from_crs(4326,crs,always_xy=True).transform(pour_point['longitude'],pour_point['latitude'])
        features.append(dict(id='pour_point',kind='pour_point',label='Hydrology point / 水文位置',xy=[list(xy)],data=pour_point))
    if not features:return dict(features=[],crs=None,background=None,bounds=None)
    points=np.concatenate([np.asarray(f['xy'],dtype=float) for f in features])
    if not np.isfinite(points).all():raise ValueError('Nonfinite map coordinates')
    margin=max(float(np.ptp(points,axis=0).max())*.1,30/crs.axis_info[0].unit_conversion_factor)
    lo=points.min(axis=0)-margin;hi=points.max(axis=0)+margin
    # Square extent makes map distances isotropic in a square viewport.
    center=(lo+hi)/2;span=float((hi-lo).max());lo=center-span/2;hi=center+span/2
    background=None;raster_source=None;t=config.get('terrain',{})
    if t.get('mode')=='local' and t.get('raster'):
        import rasterio
        from rasterio.windows import from_bounds
        from PIL import Image
        raster=safe_path(project_path.parent,t['raster'])
        with rasterio.open(raster) as ds:
            actual=CRS.from_user_input(ds.crs);horizontal=actual.sub_crs_list[0] if actual.is_compound else actual
            if not crs.equals(horizontal):raise ValueError('Map and terrain CRS differ; explicit reprojection required')
            arr=ds.read(1,window=from_bounds(*lo,*hi,ds.transform),out_shape=(700,700),boundless=True,masked=True).astype(float)
        valid=arr.compressed()
        if valid.size:
            low,high=np.percentile(valid,[2,98]);gray=np.clip((arr.filled(low)-low)/max(high-low,1e-9)*180+40,0,255).astype('uint8')
            rgba=np.stack([gray,gray,gray,np.where(np.ma.getmaskarray(arr),0,255).astype('uint8')],axis=2)
            buf=io.BytesIO();Image.fromarray(rgba).save(buf,format='PNG');background=base64.b64encode(buf.getvalue()).decode()
        raster_source=item(raster)
    inverse=Transformer.from_crs(crs,4326,always_xy=True)
    for f in features:f['wgs84']=[list(inverse.transform(*p)) for p in f['xy']]
    return dict(features=features,crs=crs.to_wkt(),crs_label=crs.to_string(),unit=crs.axis_info[0].unit_name,
        unit_to_m=crs.axis_info[0].unit_conversion_factor,bounds=[*lo,*hi],background=background,terrain_source=raster_source)


def plot_map(packet, output):
    """Standalone actual-data map for review outside the browser."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    m=packet['map']
    if not m['bounds']:return
    x0,y0,x1,y1=m['bounds'];fig,ax=plt.subplots(figsize=(8,8))
    if m['background']:
        image=Image.open(io.BytesIO(base64.b64decode(m['background'])))
        ax.imshow(image,extent=[0,x1-x0,0,y1-y0])
    for f in m['features']:
        xy=np.asarray(f['xy'])-[x0,y0];color={'section':'#ad3376','flowline':'#007d99','crossing':'#c62a20','pour_point':'#e38500'}[f['kind']]
        ax.plot(xy[:,0],xy[:,1],color=color,marker='o' if len(xy)==1 else None,lw=1)
        ax.annotate(f['label'].split('/')[0].strip(),xy[0],fontsize=7,color=color)
    ax.set(xlim=(0,x1-x0),ylim=(0,y1-y0),aspect='equal',title=packet['title']+' | Site review candidates',
        xlabel=f'Easting from {x0:.2f} ({m["unit"]})',ylabel=f'Northing from {y0:.2f} ({m["unit"]})')
    ax.annotate('Grid N',xy=(.94,.95),xytext=(.94,.85),xycoords='axes fraction',ha='center',arrowprops=dict(arrowstyle='->'))
    length=(x1-x0)/5;ax.plot([length/4,length*1.25],[length/4]*2,'k-',lw=3)
    ax.text(length/4,length/3,f'{length*m["unit_to_m"]:.1f} m',fontsize=8)
    src=m.get('terrain_source')
    fig.text(.08,.025,f'{m["crs_label"]} | {packet.get("vertical_datum")} | {packet["created_utc"][:10]}\n'
        +(src['path'] if src else 'No terrain background available')+'\nTeal: flowlines; purple: sections; red: marker; orange: hydrology point. No inundation.',fontsize=7)
    fig.tight_layout(rect=[0,.08,1,1]);fig.savefig(output,dpi=150);plt.close(fig)


def prepare(project_path,output,alignment=None,parameters=None,hydrology=None):
    path,c=load(project_path);sources=[item(path)];geometry=None;fields=[];hydrology_checks=[];pour_point=None
    for key in ['authorization']:
        if c.get(key):sources.append(item(safe_path(path.parent,c[key])))
    if c.get('terrain',{}).get('provenance'):
        sources.append(item(safe_path(path.parent,c['terrain']['provenance'])))
    if alignment:
        ap=safe_path(ROOT,alignment);geometry=read(ap)
        if geometry.get('schema_version')!='candidate_geometry_1.0' or geometry.get('project_id')!=c['project_id']:
            raise ValueError('Alignment must belong to this project')
        manifest=read(ap.parent/'manifest.json')
        if not intact(manifest['files']+geometry['sources']) or geometry['sources'][0]!=item(path):
            raise ValueError('Alignment source snapshot changed')
        sources += [item(ap),item(ap.parent/'manifest.json')]+manifest['files']+geometry['sources']
    elif c.get('geometry'):
        gp=safe_path(path.parent,c['geometry']);geometry=read(gp);sources.append(item(gp))
    for kind,candidate in [('parameter',parameters),('hydrology',hydrology)]:
        if not candidate:continue
        cp=safe_path(ROOT,candidate);data=verified_candidates(cp)
        if kind=='hydrology' and data['sources'][2]!=item(path):raise ValueError('Hydrology candidate belongs to another project')
        if kind=='hydrology':
            pour_point=data.get('reported_pour_point')
            hydrology_checks=data.get('applicability_review_items',[])
        sources += [item(cp)]+data['sources']
        for row in rows(data):
            fields.append(dict(id=kind+':'+row['key'],kind=kind,label=row['key'],required=row['required'],
                candidates=row['candidates'],source=item(cp),model_value=None))
    if not parameters and not c.get('geometry'):
        # An empty site still gets explicit fields, not one generic "geometry missing" message.
        for name,unit in [('barrel_count','count'),('shape',None),('clear_dimensions','international ft'),
                ('barrel_length','international ft'),('each_inlet_invert','international ft'),
                ('each_outlet_invert','international ft'),('vertical_datum',None),('bottom_type',None),
                ('inlet_configuration',None),('road_crest_profile','international ft'),('blockage_condition',None)]:
            fields.append(dict(id='parameter:'+name,kind='parameter',label=name,required=True,unit=unit,
                candidates=[],source=item(path),model_value=None,evidence_class='missing'))
    scenarios=[]
    for s in c['scenarios']:
        status,_=gate(path,c,s);scenarios.append(dict(id=s['id'],**status))
    gaps=[dict(category='model_gate',item=x,scenario=s['id']) for s in scenarios for x in s['blocking_items']]
    gaps += [dict(category='hydrology_applicability',item=x) for x in hydrology_checks]
    for f in fields:
        if f['required']:gaps.append(dict(category='source_review',item=f['id'],reason='Missing source value' if not f['candidates'] else 'Site applicability and use require review'))
    if geometry and geometry.get('approved_for_model') is False:
        for i,s in enumerate(geometry['cross_sections']):
            for key in ['rs','bank_stations_ft','reach_lengths_ft','expansion_contraction']:
                if s.get(key) is None:gaps.append(dict(category='candidate_geometry',item=f'section:{i}/{key}'))
    m=map_data(path,c,geometry,pour_point)
    if m.get('terrain_source'):sources.append(m['terrain_source'])
    if geometry:
        from .geometry_qa import spatial_issues
        intersections=[q['sections'] for q in spatial_issues(geometry['cross_sections']) if q['code']=='INTERSECTING_SECTIONS']
    else:intersections=[]
    for pair in intersections:gaps.append(dict(category='intersecting_sections',item=list(pair)))
    gaps += [dict(category='review',item='Crossing location, flow direction, banks, structure/road datum and flow applicability require explicit review')]
    packet=dict(schema_version='site_review_1.0',created_utc=utc(),project_id=c['project_id'],title=c['title'],
        source_project=item(path),sources=sources,map=m,fields=fields,scenario_gates=scenarios,gaps=gaps,
        vertical_datum=geometry.get('vertical_datum') if geometry else c.get('terrain',{}).get('vertical_datum'),
        intersecting_sections=intersections,status='REVIEW_REQUIRED',approved_for_model=False,engineering_acceptance='NOT_ASSESSED')
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    save(folder/'site_packet.json',packet)
    ids=[f['id'] for f in m['features']]+[f['id'] for f in fields]
    spec=dict(schema_version='site_decisions_1.0',packet=item(folder/'site_packet.json'),reviewer=None,review_basis=None,
        decisions=[dict(id=i,decision='PENDING',note=None,candidate_index=None,bank_indices=None) for i in ids])
    save(folder/'decisions.template.json',spec)
    (folder/'index.html').write_text(render_html(packet,spec),encoding='utf-8')
    plot_map(packet,folder/'review_map.png')
    save(folder/'map.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',properties=dict(id=f['id'],role=f['kind'],status='REQUIRES_REVIEW'),geometry=dict(type='Point' if len(f['wgs84'])==1 else 'LineString',coordinates=f['wgs84'][0] if len(f['wgs84'])==1 else f['wgs84'])) for f in m['features']]))
    for lang in ['EN','CN']:
        heading='Site intake and missing inputs' if lang=='EN' else '场地资料与缺项清单'
        text=['# '+heading,'','[English](INTAKE_EN.md) | [简体中文](INTAKE_CN.md)','',c['title'],'',
              '[Open local review map / 打开本地审核地图](index.html)','',
              'REVIEW_REQUIRED · approved_for_model=false · engineering_acceptance=NOT_ASSESSED','',
              'Model gates describe existing configurations. Map/source decisions do not authorize new model inputs.' if lang=='EN' else '模型门槛描述既有配置；地图及来源审核不授予新参数建模许可。','']
        text += ['- '+json.dumps(g,ensure_ascii=False) for g in gaps]
        (folder/f'INTAKE_{lang}.md').write_text('\n'.join(text),encoding='utf-8')
    save(folder/'manifest.json',dict(files=[item(p) for p in folder.iterdir() if p.is_file()],sources=sources))
    return packet


def apply_review(packet_path,spec_path,output):
    pp=safe_path(ROOT,packet_path);sp=safe_path(ROOT,spec_path);p=read(pp);s=read(sp)
    manifest=read(pp.parent/'manifest.json')
    if not intact(manifest['files']+manifest['sources']) or s.get('packet')!=item(pp):raise ValueError('Site packet or sources changed')
    if s.get('schema_version')!='site_decisions_1.0' or not isinstance(s.get('reviewer'),str) or not s['reviewer'].strip() or not s.get('review_basis'):
        raise ValueError('Explicit reviewer and review basis required')
    available={f['id']:f for f in p['map']['features']+p['fields']};ds=s.get('decisions',[])
    if len(ds)!=len(available) or {d['id'] for d in ds}!=set(available):raise ValueError('One decision for every map/parameter item required')
    selected=[];selected_sections=set()
    for d in ds:
        feature=available[d['id']];choice=d.get('decision')
        if choice not in ['PENDING','RETAIN_CANDIDATE','REJECT','DEFER']:raise ValueError('Unsupported site review decision')
        if choice!='PENDING' and not d.get('note'):raise ValueError('Every decision requires a reason')
        value=None
        if choice=='RETAIN_CANDIDATE':
            if feature['kind'] in ['parameter','hydrology']:
                i=d.get('candidate_index')
                if type(i)!=int or not 0<=i<len(feature['candidates']):raise ValueError('Cannot select missing/invented source values')
                value=copy.deepcopy(feature['candidates'][i])
            else:
                value=copy.deepcopy(feature['data'])
                if feature['kind']=='section':
                    selected_sections.add(int(feature['id'].split(':')[1]))
                    banks=d.get('bank_indices')
                    if banks is not None:
                        n=len(value['station_ft'])
                        if not isinstance(banks,list) or len(banks)!=2 or not all(type(i)==int for i in banks) or not 0<banks[0]<banks[1]<n-1:
                            raise ValueError('Banks must select two interior, ordered sampled station points')
                        value['bank_stations_ft']=[value['station_ft'][i] for i in banks]
                        value['bank_provenance']=dict(method='operator_selected_from_terrain_section',reviewer=s['reviewer'],note=d['note'])
                if d.get('candidate_index') is not None:raise ValueError('Map items cannot select source values')
        elif d.get('candidate_index') is not None or d.get('bank_indices') is not None:
            raise ValueError('Unselected items must retain null selections')
        if feature['kind']!='section' and d.get('bank_indices') is not None:raise ValueError('Bank selection only applies to sections')
        selected.append(dict(id=d['id'],decision=choice,note=d.get('note'),selected_candidate=value,model_value=None,approved_for_model=False))
    crossing=[pair for pair in p['intersecting_sections'] if all(i in selected_sections for i in pair)]
    result=dict(schema_version='reviewed_site_inputs_1.0',created_utc=utc(),status='CANDIDATES_REVIEWED_MODEL_INPUTS_PENDING',
        project_id=p['project_id'],sources=[item(pp),item(sp),item(pp.parent/'manifest.json')],reviewer=s['reviewer'],review_basis=s['review_basis'],
        reviewer_identity='OPERATOR_ATTESTED',fields=selected,remaining_intersecting_sections=crossing,
        unresolved_model_gates=p['scenario_gates'],model_requirements=['Reviewed RS, reach lengths, losses, structure geometry, road crest, boundaries, units/datum and site-specific authorization',
        'Transcription and map decisions require separate site-applicability and conditional-use review before formal configuration'],
        approved_for_model=False,engineering_acceptance='NOT_ASSESSED')
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Choose a new reviewed-input output; previous reviews are immutable')
    save(out,result);return result
