"""Bilingual batch review from verified immutable attempts, never global outputs."""
import csv
import math
import textwrap
from pathlib import Path
import h5py
import numpy as np
import rasterio
from rasterio.windows import from_bounds, bounds as window_bounds
from pyproj import CRS,Transformer
from docx.shared import Inches
from .common import ROOT, intact, item, lock, read, rel, safe_path, save, utc
from .queue import validate_receipt
from .qa import BASE
from .report import document, table, fmt, render


def snapshot_source(receipt,summary,original):
    """Prefer the immutable pre-solver snapshot, not a subsequently edited site file."""
    hyd=summary.get('hydraulics')
    if hyd:
        folder=(ROOT/hyd['raw_hdf']['path']).parent.parent
        manifest=read(folder/'manifest.json')
        match=[e for e in manifest['input_snapshots'] if e['path'].endswith('/inputs_before/'+rel(original))]
        if len(match)==1 and intact(match):return match[0]
    match=[e for e in receipt['inputs'] if e['path']==rel(original)]
    if len(match)==1 and intact(match):return match[0]
    raise ValueError('Verified map input unavailable: '+rel(original))


def profile_plot(summary,output):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    hyd=summary['hydraulics']
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as h:
        stations=[v['Station'].decode().strip() for v in h['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        info=h['Geometry/Cross Sections/Station Elevation Info'][:];points=h['Geometry/Cross Sections/Station Elevation Values'][:]
        bed=[float(points[start:start+count,1].min()) for start,count in info]
        values=h[BASE+'/Cross Sections/Water Surface'][:]
        if len(stations)!=len(bed) or len(values)!=len(hyd['profiles']):raise ValueError('Profile figure schema/identity mismatch')
    fig,ax=plt.subplots(figsize=(8,3.1));x=np.arange(len(stations))
    ax.plot(x,bed,color='#6b553b',label='Section minimum elevation',lw=1.3)
    for p,w in zip(hyd['profiles'],values):ax.plot(x,w,marker='.',label=p['profile_id']+' WSE')
    step=max(1,math.ceil(len(stations)/18));ax.set_xticks(x[::step],stations[::step],rotation=45,ha='right',fontsize=7)
    ax.set(ylabel='Elevation (international ft)',xlabel='Cross-section order, upstream to downstream (RS labels; not a distance scale)')
    ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2);fig.tight_layout();fig.savefig(output,dpi=160);plt.close(fig)
    return dict(status='DRAWN_FROM_VERIFIED_HDF',image=item(output),source=hyd['raw_hdf'],station_count=len(stations),datum=hyd['datum'])


def terrain_map(receipt,summary,output):
    c=summary['configuration'];t=summary.get('terrain',{});raster=t.get('raster')
    if not raster:return dict(status='NOT_AVAILABLE',reason='No georeferenced DEM was used; no geographic location is invented')
    raster_source=snapshot_source(receipt,summary,ROOT/raster['path']) if summary.get('hydraulics') else raster
    if not intact([raster_source]):raise ValueError('Map DEM hash mismatch')
    geometry=None;geometry_source=None
    if c.get('geometry'):
        original=safe_path((ROOT/receipt['project']).parent,c['geometry'])
        geometry_source=snapshot_source(receipt,summary,original);geometry=read(ROOT/geometry_source['path'])
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with rasterio.open(ROOT/raster_source['path']) as src:
        crs=CRS.from_user_input(src.crs)
        if not crs.is_projected:raise ValueError('Map requires a projected DEM CRS with known axis units')
        unit=crs.axis_info[0].unit_name;factor=crs.axis_info[0].unit_conversion_factor
        lines=[];centers=[]
        if geometry:
            transform=Transformer.from_crs(geometry['horizontal_crs'],crs,always_xy=True)
            for xs in geometry['cross_sections']:
                points=np.array(xs['cutline_xy']);xx,yy=transform.transform(points[:,0],points[:,1]);lines.append(np.column_stack([xx,yy]))
                centers.append(transform.transform(*xs['center_xy']))
        if lines:
            pts=np.vstack(lines);margin=25/factor
            extent=[pts[:,0].min()-margin,pts[:,1].min()-margin,pts[:,0].max()+margin,pts[:,1].max()+margin]
        else:extent=list(src.bounds)
        window=from_bounds(*extent,src.transform).round_offsets().round_lengths()
        height=max(1,min(1400,int(window.height)));width=max(1,round(window.width/window.height*height))
        if width>1800:height=max(1,round(height*1800/width));width=1800
        z=src.read(1,window=window,out_shape=(height,width),boundless=True,masked=True)
        if z.count()==0:raise ValueError('No valid terrain in map extent')
        left,bottom,right,top=window_bounds(window,src.transform)
        fig,ax=plt.subplots(figsize=(8,6.1));im=ax.imshow(z,extent=[left,right,bottom,top],cmap='terrain',interpolation='nearest')
        for i,line in enumerate(lines):
            ax.plot(line[:,0],line[:,1],color='#1d5c91',lw=.8,label='Model cross sections' if i==0 else None)
            if i%3==0:ax.text(line[0,0],line[0,1],str(geometry['cross_sections'][i]['rs']),fontsize=6,color='#14344d')
        if centers:
            centers=np.array(centers);ax.plot(centers[:,0],centers[:,1],'k--',lw=1,label='Model section-centre flow path')
            ax.annotate('',xy=centers[1],xytext=centers[0],arrowprops=dict(arrowstyle='->',color='black'))
        if c.get('location'):
            loc=c['location'];xy=Transformer.from_crs(4326,crs,always_xy=True).transform(loc['longitude'],loc['latitude'])
            ax.plot(*xy,'r+',ms=10,label='Source coordinate (conditional crossing)')
        scale_choices=[1,2,5,10,20,50,100,200,500,1000,2000]
        scale=max([v for v in scale_choices if v<(right-left)*factor*.25],default=(right-left)*factor*.2)
        sx=left+(right-left)*.08;sy=bottom+(top-bottom)*.07
        ax.plot([sx,sx+scale/factor],[sy,sy],color='black',lw=3);ax.text(sx,sy+(top-bottom)*.02,f'{scale:g} m',fontsize=8)
        ax.annotate('Grid N',xy=(.93,.94),xytext=(.93,.80),xycoords='axes fraction',ha='center',fontsize=8,arrowprops=dict(arrowstyle='->'))
        ax.set(xlim=(left,right),ylim=(bottom,top),xlabel='Easting ('+unit+')',ylabel='Northing ('+unit+')',title=c['project_id']+' / external terrain and model geometry')
        ax.ticklabel_format(style='plain',useOffset=False);ax.tick_params(axis='x',labelrotation=25,labelsize=7);ax.tick_params(axis='y',labelsize=7)
        if lines or c.get('location'):ax.legend(fontsize=6,loc='upper left')
        fig.colorbar(im,ax=ax,label='DEM elevation: '+str(t.get('vertical_unit','UNREVIEWED'))+' / '+str(t.get('vertical_datum','UNREVIEWED')))
        horizontal=crs.to_2d();authority=horizontal.to_authority()
        crs_label=':'.join(authority) if authority else horizontal.name
        footer='Horizontal CRS: '+crs_label+' | Generated UTC '+utc()[:10]+'\nSource: external DEM SHA-256 '+raster_source['sha256'][:20]+'... | No inundation extent'
        fig.text(.04,.018,'\n'.join(textwrap.fill(line,105) for line in footer.splitlines()),fontsize=7)
        fig.tight_layout(rect=[0,.07,1,1]);fig.savefig(output,dpi=160);plt.close(fig)
    return dict(status='DRAWN_EXTERNAL_TERRAIN_ONLY',image=item(output),raster=raster_source,geometry=geometry_source,
        crs=crs_label,crs_wkt=crs.to_wkt(),horizontal_unit=unit,scale_m=scale,vertical_unit=t.get('vertical_unit'),vertical_datum=t.get('vertical_datum'),
        valid_display_fraction=float(z.count()/z.size),source_metadata=t.get('metadata'),generated_utc=utc(),
        limitation='Source/model geometry is conditional; this is not a flood extent or 2D result. DEM does not measure buried inverts.')


def collect(queue_output,folder):
    queue_output=safe_path(ROOT,queue_output)
    with lock(queue_output/'queue.lock'):
        state=read(queue_output/'queue_state.json');source=item(queue_output/'queue_state.json')
        save(folder/'queue_snapshot.json',state)
    jobs=[]
    for jid,history in state['jobs'].items():
        latest=history[-1] if history else dict(status='PENDING')
        row=dict(job_id=jid,queue_status=latest['status'],attempt_count=len(history),
            history=[dict(id=a.get('id'),status=a['status'],error=a.get('error')) for a in history],
            calculation_status=latest.get('calculation_status','NOT_VERIFIED'),hydraulics=None,errors=list(latest.get('errors',[])),
            map=dict(status='NOT_AVAILABLE',reason='No verified attempt receipt'),profile_plot=None)
        if latest.get('error'):row['errors'].append(latest['error'])
        if latest.get('receipt'):
            receipt,s=validate_receipt(latest['receipt'],latest.get('identity',{}).get('evidence',{}).get('job'))
            row.update(receipt=latest['receipt'],summary=receipt['summary'],title=s['configuration']['title'],
                case_kind=s['configuration']['case_kind'],calculation_status=s['calculation_status'],
                hydraulics=s.get('hydraulics'),gate=s['gate'],solver_reused=s['solver_reused'],report_status=receipt['report_status'])
            figures=folder/'figures'/jid;figures.mkdir(parents=True)
            if s.get('hydraulics'):row['profile_plot']=profile_plot(s,figures/'profiles.png')
            row['map']=terrain_map(receipt,s,figures/'terrain.png')
        jobs.append(row)
    return dict(schema_version='1.0',queue_id=state['queue_id'],created_utc=utc(),queue_source_at_generation=source,
        queue_snapshot=item(folder/'queue_snapshot.json'),jobs=jobs,
        engineering_acceptance='NOT_ASSESSED',new_solver_calls_by_report=0)


def generate(queue_output,output):
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    data=collect(queue_output,folder);save(folder/'batch_data.json',data)
    data=read(folder/'batch_data.json');data_entry=item(folder/'batch_data.json')
    rows=[]
    for job in data['jobs']:
        hyd=job['hydraulics']
        for p in hyd['profiles'] if hyd else [None]:
            rows.append(dict(job_id=job['job_id'],case_kind=job.get('case_kind'),queue_status=job['queue_status'],
                calculation_status=job['calculation_status'],run_id=hyd['run_id'] if hyd else None,
                profile_id=p['profile_id'] if p else None,flow_cfs=p['flow_cfs'] if p else None,
                headwater_wse_ft=p['metrics']['headwater_wse_ft'] if p else None,
                tailwater_wse_ft=p['metrics']['tailwater_wse_ft'] if p else None,datum=hyd['datum'] if hyd else None,
                summary_sha256=job.get('summary',{}).get('sha256'),engineering_acceptance='NOT_ASSESSED'))
    with (folder/'batch_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    from .batch_content import build
    from . import __version__
    variants=[('en','full','Batch_Report_EN'),('zh-CN','full','Batch_Report_CN'),('en','summary','Batch_Summary_EN')]
    manifest=dict(schema_version='batch_reports_2.0',created_utc=utc(),generator_version=__version__,status='GENERATED_PENDING_VISUAL_REVIEW',data=data_entry,results=item(folder/'batch_results.csv'),reports=[],engineering_acceptance='NOT_ASSESSED',new_solver_calls_by_report=0)
    for language,detail,name in variants:
        doc=folder/(name+'.docx');build(data,data_entry,language,detail).save(doc)
        pdf,n,pages=render(doc);manifest['reports'].append(dict(language=language,detail=detail,docx=item(doc),pdf=item(pdf),page_count=n,rendered_pages=[item(p) for p in pages],render_evidence=item(doc.parent/'qa'/doc.stem/'render_manifest.json')))
    save(folder/'batch_report_manifest.json',manifest);return manifest


def verify(output):
    folder=safe_path(ROOT,output);m=read(folder/'batch_report_manifest.json')
    entries=[m['data'],m['results']]+[e for r in m['reports'] for e in [r['docx'],r['pdf'],r['render_evidence'],*r['rendered_pages']]]
    if not intact(entries):raise ValueError('Batch report data or document artifact changed')
    data=read(ROOT/m['data']['path'])
    if not intact([data['queue_snapshot']]):raise ValueError('Batch queue snapshot changed')
    for job in data['jobs']:
        if job.get('receipt'):
            receipt,summary=validate_receipt(job['receipt'])
            if receipt['summary']!=job['summary'] or summary.get('hydraulics')!=job['hydraulics']:raise ValueError('Batch differs from source attempt')
        for key in ['map','profile_plot']:
            if job.get(key) and job[key].get('image') and not intact([job[key]['image']]):raise ValueError('Batch figure changed')
    return dict(status='PASS_INTEGRITY_ONLY',manifest=item(folder/'batch_report_manifest.json'),visual_review='SEE_SEPARATE_PAGE_REVIEW',engineering_acceptance='NOT_ASSESSED')
