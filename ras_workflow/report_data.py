"""Readable-report data and figures from bound native outputs and input snapshots."""
import math
from pathlib import Path
import h5py
import numpy as np
from .common import ROOT, intact, item, read, rel, safe_path, save, utc
from .qa import BASE, number, verified_profiles


def collect(summary_path, comparisons=()):
    summary_path=safe_path(ROOT,summary_path);s=read(summary_path);h=s['hydraulics']
    verified_profiles(h)
    if s.get('hydraulic_results') and (not intact([s['hydraulic_results']]) or read(ROOT/s['hydraulic_results']['path'])!=h):
        raise ValueError('Report summary differs from sealed hydraulic extraction')
    sources=[item(summary_path),h['raw_hdf'],h['raw_controller']]
    controller=read(ROOT/h['raw_controller']['path'])
    rows=[]
    with h5py.File(ROOT/h['raw_hdf']['path']) as f:
        attrs=f['Geometry/Cross Sections/Attributes'][:]
        info=f['Geometry/Cross Sections/Station Elevation Info'][:]
        points=f['Geometry/Cross Sections/Station Elevation Values'][:]
        output_stations=[r['Station'].decode().strip() for r in f['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
        geometry_stations=[r['RS'].decode().strip() for r in attrs]
        if output_stations!=geometry_stations or len(info)!=len(attrs):raise ValueError('Report geometry/output order mismatch')
        for i,(a,(start,count)) in enumerate(zip(attrs,info)):
            xy=points[start:start+count]
            rows.append(dict(rs=geometry_stations[i],station_ft=xy[:,0].astype(float).tolist(),elevation_ft=xy[:,1].astype(float).tolist(),
                banks_ft=[float(a['Left Bank']),float(a['Right Bank'])],channel_length_ft=number(a['Len Channel']),profiles={}))
        for pi,p in enumerate(h['profiles']):
            w=f[BASE+'/Cross Sections/Water Surface'][pi];eg=f[BASE+'/Cross Sections/Energy Grade'][pi]
            for i,row in enumerate(rows):
                matches=[v for v in controller['rows'] if v['profile']==p['profile_id'] and v['station']==row['rs'] and not v['node_type']]
                if len(matches)!=1:raise ValueError('Ambiguous native section result')
                m=matches[0]['metrics'];row['profiles'][p['profile_id']]=dict(wse_ft=float(w[i]),egl_ft=float(eg[i]),
                    critical_wse_ft=number(m.get('Crit W.S.')),velocity_fts=number(m.get('Vel Chnl')),
                    froude=number(m.get('Froude # Chl')),min_error_ft=number(m.get('Min Error')),
                    left_freeboard_ft=number(m.get('L. Freeboard')),right_freeboard_ft=number(m.get('R. Freeboard')))
    geometry=None;geometry_source=None;raster_source=None;native_inputs=None;native_input_error=None
    mp=(ROOT/h['raw_hdf']['path']).parent.parent/'manifest.json'
    if mp.exists():
        manifest=read(mp)
        if manifest.get('run_id')!=h['run_id']:raise ValueError('Input snapshot belongs to another run')
        snapshots=manifest.get('input_snapshots',[])
        bound=[]
        for e in snapshots:
            if Path(e['path']).suffix!='.json' or not intact([e]):continue
            try:
                if read(ROOT/e['path'])==s['configuration']:bound.append(e)
            except (ValueError,OSError):continue
        if not bound:raise ValueError('Report configuration differs from native-run input snapshots')
        sources+=[item(mp),bound[0]]
        if manifest.get('native_before'):
            native=manifest.get('native_before',[])
            if native and not intact(native):raise ValueError('Native input snapshots changed')
            projects=[e for e in native if Path(e['path']).suffix.lower()=='.prj']
            if len(projects)==1:
                if h.get('model_type') == 'river':
                    from .report_native_river import inspect
                else:
                    from .native_review import inspect
                try:native_inputs=inspect(ROOT/projects[0]['path'])
                except (ValueError,IndexError,StopIteration,OSError) as e:native_input_error=str(e)
                sources+=native
        candidates=[e for e in snapshots if s['configuration'].get('geometry') and Path(e['path']).name==Path(s['configuration']['geometry']).name]
        if len(candidates)==1:
            geometry_source=candidates[0]
            if not intact([geometry_source]):raise ValueError('Report geometry snapshot changed')
            geometry=read(ROOT/geometry_source['path']);sources+=[geometry_source]
            from .bank_reassessment import selection_sources
            sources+=selection_sources(geometry)
        raster=s.get('terrain',{}).get('raster')
        if raster:
            matched=[e for e in snapshots if e['path'].endswith('/inputs_before/'+raster['path']) and e['sha256']==raster['sha256']]
            raster_source=matched[0] if len(matched)==1 else raster
            if not intact([raster_source]):raise ValueError('Report terrain source changed')
            sources.append(raster_source)
    map_geometry=geometry
    if map_geometry is None and raster_source and s['configuration'].get('delivery',{}).get('horizontal_crs'):
        # Imported models retain their native-input reporting branch. A separate
        # map object reads the actual result cutlines and the run-bound CRS.
        from .delivery_spatial import extract,interpolate_line
        crs=s['configuration']['delivery']['horizontal_crs']
        spatial=extract(ROOT/h['raw_hdf']['path'],crs)
        map_geometry=dict(horizontal_crs=crs,cross_sections=[dict(rs=f['properties']['rs'],
            cutline_xy=f['geometry']['coordinates'],center_xy=interpolate_line(f['geometry']['coordinates'],.5))
            for f in spatial['layers']['cross_sections']])
    diagnostics=None
    if h.get('diagnostics'):
        if not intact([h['diagnostics']]):raise ValueError('Report diagnostic evidence changed')
        diagnostics=read(ROOT/h['diagnostics']['path']);sources.append(h['diagnostics'])
        if diagnostics['run_id']!=h['run_id'] or not intact(diagnostics['sources']):raise ValueError('Report diagnostic source mismatch')
    supplement=None
    if s.get('native_supplement'):
        from .app_outputs import validate as validate_outputs,diagnostics as supplemented_qa
        supplement=validate_outputs(s['native_supplement']);diagnostics=supplemented_qa(h,supplement)
        sources+=[s['native_supplement']]+supplement['files']
        if supplement.get('automatic_receipt'):sources.append(supplement['automatic_receipt'])
    import re
    language_review=[]
    for i,g in enumerate((geometry or {}).get('structure',{}).get('groups',[])):
        for key in ('bottom_type','inlet_description','blockage_basis'):
            if re.search(r'[\u3400-\u9fff]',str(g.get(key,''))):language_review.append(dict(group=i+1,field=key,status='ENGLISH_TRANSLATION_PENDING',original=g[key]))
    compared=[];references=[]
    for path in comparisons or []:
        entry=item(safe_path(ROOT,path));comp=read(ROOT/entry['path'])
        if comp.get('schema_version')=='public_csv_comparison_1.0':
            if not intact(comp.get('sources',[])) or len(comp.get('sources',[]))!=5 or comp.get('run_id')!=h['run_id'] or item(summary_path) not in comp['sources']:
                raise ValueError('Public comparison sources changed or belong to another report')
            from .public_case import compare as reference_compare
            from tempfile import TemporaryDirectory
            with TemporaryDirectory(dir=ROOT/'status',prefix='report_reference_') as tmp:
                actual=reference_compare(comp['sources'][0]['path'],summary_path,Path(tmp)/'comparison.json')
            if {k:v for k,v in actual.items() if k!='created_utc'}!={k:v for k,v in comp.items() if k!='created_utc'}:
                raise ValueError('Public comparison values differ from original evidence')
            references.append(comp);sources+=[entry]+comp['sources'];continue
        if not intact(comp.get('sources',[])) or len(comp['sources'])!=2:raise ValueError('Comparison sources changed')
        if item(summary_path)['sha256'] not in [v['sha256'] for v in comp['sources']]:raise ValueError('Comparison is unrelated to this report')
        # Recompute the comparison from real outputs; a modified comparison JSON
        # never becomes a report number simply because its sources still exist.
        from .qa import compare
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(dir=ROOT/'status',prefix='report_compare_') as tmp:
            actual=compare(comp['sources'][0]['path'],comp['sources'][1]['path'],Path(tmp)/'comparison.json')
        if comp!=actual:raise ValueError('Comparison values differ from native outputs')
        compared.append(comp);sources+=[entry]+comp['sources']
    studies=[];river_checks={}
    if h.get('model_type') == 'river':
        from .report_studies import collect as collect_studies
        studies, study_sources = collect_studies(summary_path, s)
        sources += study_sources
        from .river_review_report import collect as collect_river_checks
        river_checks,check_sources=collect_river_checks(summary_path,s)
        sources+=check_sources
    from .field_results import collect as field_results
    feedback,feedback_sources=field_results(s)
    sources+=feedback_sources
    revision=None
    if s['configuration'].get('revision_origin'):
        from .app_revision import compare as compare_revision
        revision=compare_revision(dict(parent_revision=s['configuration']['revision_origin']),s)
        sources+=revision.get('sources',[])
    from .purpose_acceptance import evaluate
    reviewed_events=list(river_checks.get('events',[]))
    if feedback and feedback['mode']=='event':
        from .field_results import verified_observations
        reviewed_events.extend(verified_observations(feedback))
    purpose_decision=evaluate(s,reviewed_events,revision)
    return dict(purpose_decision=purpose_decision, studies=studies, field_feedback=feedback, river_checks=river_checks, revision_comparison=revision,schema_version='readable_report_data_1.0',created_utc=utc(),summary=s,sections=rows,
        geometry=geometry,map_geometry=map_geometry,geometry_source=geometry_source,raster_source=raster_source,diagnostics=diagnostics,
        language_review=language_review,native_supplement=supplement,comparisons=compared,reference_comparisons=references,native_inputs=native_inputs,native_input_error=native_input_error,
        sources=sources,report_generation_is_solver_run=False)


def plot_style(language="en"):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,
        'legend.fontsize':8,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    if language == 'zh-CN':
        from matplotlib.font_manager import fontManager
        installed = {font.name for font in fontManager.ttflist}
        choices = ['Microsoft YaHei', 'Noto Sans CJK SC', 'SimHei', 'SimSun']
        font = next((name for name in choices if name in installed), None)
        if font is None:
            raise ValueError('Chinese report charts require Microsoft YaHei or Noto Sans CJK SC')
        plt.rcParams['font.family'] = [font, 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    return plt


def figures(data, folder, language="en"):
    folder.mkdir(parents=True,exist_ok=False);plt=plot_style(language)
    tr=lambda en,zh:zh if language=='zh-CN' else en
    s=data['summary'];h=s['hydraulics'];rows=data['sections'];result={}
    unit=h.get('unit','international ft');unit=tr(unit,{'international ft':'国际英尺','international foot':'国际英尺','US survey foot':'美制测量英尺','m':'米'}.get(unit,unit));stations=[r['rs'] for r in rows];x=np.arange(len(rows))
    fig,(ax,fr)=plt.subplots(2,1,figsize=(8.1,4.9),sharex=True,gridspec_kw={'height_ratios':[2.2,1]})
    ax.plot(x,[min(r['elevation_ft']) for r in rows],color='#785c40',lw=1.5,label=tr('Section minimum','断面最低点'))
    for pi,p in enumerate(h['profiles']):
        name=p['profile_id'];color=plt.get_cmap('tab10')(pi%10)
        ax.plot(x,[r['profiles'][name]['wse_ft'] for r in rows],color=color,lw=1.6,marker='.',label=name+tr(' water surface',' 水位'))
        ax.plot(x,[r['profiles'][name]['egl_ft'] for r in rows],color=color,ls='--',lw=1,label=name+tr(' energy grade',' 能量线'))
        fr.plot(x,[r['profiles'][name]['froude'] for r in rows],color=color,marker='.',lw=1)
    us,ds=h['profiles'][0]['headwater_rs'],h['profiles'][0]['tailwater_rs']
    if h.get('model_type')!='river' and us in stations and ds in stations:
        for a in [ax,fr]:a.axvspan(stations.index(us),stations.index(ds),color='#edd8b2',alpha=.4)
    ax.set_ylabel(tr('Elevation (','高程 (')+unit+')');ax.legend(ncol=2,loc='best');ax.grid(alpha=.2)
    fr.axhline(1,color='#9c4a36',ls='--',lw=1);fr.set_ylabel(tr('Channel Froude','主槽弗劳德数'));fr.grid(alpha=.2)
    tick=np.unique(np.r_[np.arange(0,len(rows),max(1,math.ceil(len(rows)/14))),len(rows)-1])
    fr.set_xticks(tick,[stations[i] for i in tick],rotation=35,ha='right',fontsize=8)
    fr.set_xlabel(tr('Upstream to downstream section order / RS labels (not a distance scale)','上游至下游断面顺序 / RS 编号（非距离比例）'))
    fig.tight_layout();path=folder/'longitudinal.png';fig.savefig(path,dpi=190);plt.close(fig);result['longitudinal']=item(path)
    panels=[]
    for begin in range(0,len(rows),4):
        fig,axes=plt.subplots(2,2,figsize=(8.1,6.1));axes=axes.ravel()
        for ax,row in zip(axes,rows[begin:begin+4]):
            xx=np.asarray(row['station_ft']);zz=np.asarray(row['elevation_ft']);ax.plot(xx,zz,color='#785c40',lw=1.4,label=tr('Ground','地面'))
            for b,side in zip(row['banks_ft'],['Left bank','Right bank']):
                ax.axvline(b,color='#95652b',ls=':',lw=1);ax.plot(b,np.interp(b,xx,zz),'o',color='#95652b',ms=3)
            for pi,p in enumerate(h['profiles']):
                w=row['profiles'][p['profile_id']]['wse_ft'];color=plt.get_cmap('tab10')(pi%10)
                ax.axhline(w,color=color,lw=1.1,label=p['profile_id']+tr(' WSE',' 水位'))
            ax.set_title('RS '+row['rs']+((tr('  /  Upstream',' / 上游端') if row['rs']==us else tr('  /  Downstream',' / 下游端') if row['rs']==ds else '') if h.get('model_type')=='river' else ('  /  HW' if row['rs']==us else '  /  TW' if row['rs']==ds else '')))
            ax.set(xlabel=tr('Station (','站距 (')+unit+')',ylabel=tr('Elevation (','高程 (')+unit+')');ax.grid(alpha=.15);ax.legend(loc='best',fontsize=7)
        for ax in axes[len(rows[begin:begin+4]):]:ax.set_visible(False)
        fig.tight_layout(pad=1.6);path=folder/f'sections_{begin+1:03d}.png';fig.savefig(path,dpi=190);plt.close(fig)
        panels.append(dict(image=item(path),stations=stations[begin:begin+4]))
    result['sections']=panels
    g=data.get('map_geometry',data['geometry']);raster=data['raster_source']
    result['terrain']=dict(status='NOT_AVAILABLE',reason='No verified georeferenced terrain and geometry snapshot for this run')
    if raster and g:
        import rasterio
        from rasterio.windows import from_bounds,bounds
        from pyproj import CRS,Transformer
        with rasterio.open(ROOT/raster['path']) as dem:
            crs=CRS.from_user_input(dem.crs);crs=crs.sub_crs_list[0] if crs.is_compound else crs
            if not crs.is_projected:raise ValueError('Report terrain map requires a projected CRS')
            transform=Transformer.from_crs(g['horizontal_crs'],crs,always_xy=True)
            cuts=[np.column_stack(transform.transform(*np.asarray(r['cutline_xy']).T)) for r in g['cross_sections']]
            allpoints=np.vstack(cuts);pad=20/crs.axis_info[0].unit_conversion_factor
            lo=allpoints.min(axis=0)-pad;hi=allpoints.max(axis=0)+pad
            win=from_bounds(lo[0],lo[1],hi[0],hi[1],dem.transform);aspect=win.width/win.height
            height=min(1000,max(1,int(win.height)));width=max(1,int(height*aspect))
            if width>1200:height=max(1,int(height*1200/width));width=1200
            z=dem.read(1,window=win,out_shape=(height,width),boundless=True,masked=True)
            if not z.count():raise ValueError('Report map has no valid DEM data')
            left,bottom,right,top=bounds(win,dem.transform);origin=np.floor(lo/1000)*1000
            fig,ax=plt.subplots(figsize=(8.1,5.5));im=ax.imshow(z,extent=[left-origin[0],right-origin[0],bottom-origin[1],top-origin[1]],cmap='terrain',interpolation='nearest')
            wet={v for p in h['profiles'] for v in p['qa']['wet_edges']}
            labelled_indices=set(np.linspace(0,len(cuts)-1,min(len(cuts),12),dtype=int))
            for i,(cut,row) in enumerate(zip(cuts,g['cross_sections'])):
                cut=cut-origin;iswet=any(abs(float(rs)-float(row['rs']))<.005 for rs in wet)
                ax.plot(*cut.T,color='#b24433' if iswet else '#234f73',lw=1)
                if i in labelled_indices:
                    ax.text(*cut[0],str(row['rs']),fontsize=6.5,color='#162f43',bbox=dict(facecolor='white',alpha=.6,pad=.3,edgecolor='none'))
            centres=np.array([transform.transform(*r['center_xy']) for r in g['cross_sections']])-origin
            ax.plot(*centres.T,'k--',lw=.8,label=tr('Section-centre connection (indicative)','断面中心连线（示意）'))
            if len(centres)>1:ax.annotate('',xy=centres[1],xytext=centres[0],arrowprops=dict(arrowstyle='->',lw=1.5))
            ax.plot([],[],color='#234f73',label=tr('Model cross section','模型断面'));ax.plot([],[],color='#b24433',label=tr('Wet edge in at least one profile','至少一个工况的断面边缘过水'))
            ax.set(xlabel=tr(f'Easting offset ({crs.axis_info[0].unit_name})',f'东坐标相对值（{crs.axis_info[0].unit_name}）'),ylabel=tr(f'Northing offset ({crs.axis_info[0].unit_name})',f'北坐标相对值（{crs.axis_info[0].unit_name}）'),aspect='equal')
            ax.annotate(tr('Grid N','网格北'),xy=(.90,.94),xytext=(.90,.80),xycoords='axes fraction',ha='center',fontsize=8,arrowprops=dict(arrowstyle='->'))
            length=(right-left)*crs.axis_info[0].unit_conversion_factor*.2
            scale=max([v for v in [1,2,5,10,20,50,100,200,500] if v<=length],default=length)
            xx=left-origin[0]+(right-left)*.08;yy=bottom-origin[1]+(top-bottom)*.06
            ax.plot([xx,xx+scale/crs.axis_info[0].unit_conversion_factor],[yy,yy],'k-',lw=2);ax.text(xx,yy+(top-bottom)*.025,f'{scale:g} m',fontsize=8)
            ax.legend(loc='lower center',bbox_to_anchor=(.5,1.01),ncol=1,fontsize=7)
            fig.colorbar(im,ax=ax,shrink=.8,label=tr('DEM elevation (','DEM 高程 (')+str(s['terrain'].get('vertical_unit'))+')')
            fig.tight_layout();path=folder/'terrain.png';fig.savefig(path,dpi=190);plt.close(fig)
            result['terrain']=dict(status='DRAWN_FROM_BOUND_INPUTS',image=item(path),horizontal_crs=crs.to_string(),origin=origin.tolist())
    result['comparisons']=[]
    for ci,comp in enumerate(data['comparisons']):
        fig,ax=plt.subplots(figsize=(8.1,3.2))
        for name in dict.fromkeys(r['profile'] for r in comp['cross_section_differences']):
            rr=[r for r in comp['cross_section_differences'] if r['profile']==name]
            ax.plot(range(len(rr)),[r['delta_wse_ft'] for r in rr],marker='.',label=name)
            ticks=np.arange(0,len(rr),max(1,math.ceil(len(rr)/12)));ax.set_xticks(ticks,[rr[i]['station'] for i in ticks],rotation=30,ha='right')
        ax.axhline(0,color='gray',lw=.8);ax.set(xlabel=tr('Matched section order / RS','匹配断面顺序 / RS'),ylabel=tr('Candidate minus baseline WSE (ft)','方案减基准水位（ft）'));ax.grid(alpha=.2);ax.legend();fig.tight_layout()
        path=folder/f'comparison_{ci+1}.png';fig.savefig(path,dpi=190);plt.close(fig);result['comparisons'].append(item(path))
    return result
