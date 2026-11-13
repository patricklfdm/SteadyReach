"""Two self-contained review folders from one verified, immutable solver run.

Delivery readiness is separate from hydraulic QA and engineering acceptance.
No prior Mapper results, screenshots, or computed values are used as new output.
"""
from pathlib import Path
import json, math, os, shutil, subprocess
import h5py
import rasterio
from pyproj import CRS
from .common import ROOT, read, save, sha, item, intact, rel, safe_path, utc, digest, lock
from . import delivery_spatial as spatial

SCHEMA='site_delivery_1.0'


def horizontal_crs(value):
    crs=CRS.from_user_input(value)
    return crs.sub_crs_list[0] if crs.is_compound else crs


def register(summary,receipt):
    """Keep new delivery editions outside immutable calculation attempts."""
    path=ROOT/'status/delivery_catalogs'/digest(rel(summary))/'catalog.json'
    with lock(path.parent/'catalog.lock'):
        data=read(path) if path.exists() else dict(summary=item(summary),editions=[])
        if data['summary']!=item(summary):raise ValueError('Delivery summary changed')
        data['editions'].append(item(receipt));save(path,data)


def latest(summary):
    path=ROOT/'status/delivery_catalogs'/digest(rel(summary))/'catalog.json'
    if not path.exists():return None
    data=read(path)
    if data['summary']!=item(summary) or not data['editions']:raise ValueError('Delivery catalogue changed')
    entry=data['editions'][-1]
    if not intact([entry]):raise ValueError('Delivery receipt changed')
    result=read(ROOT/entry['path'])
    for key in ['complete','minimal']:
        if not intact([result[key]['manifest']]):raise ValueError('Delivery package manifest changed')
        verify(ROOT/result[key]['path'])
    return dict(result,receipt=entry)


def settings_for(project):
    project=Path(project);path=project.parent/'delivery.settings.json'
    if path.exists():return read(path)
    config=read(project);settings=dict(config.get('delivery',{}))
    if not settings.get('horizontal_crs') and config.get('geometry'):
        g=read(safe_path(project.parent,config['geometry']))
        if g.get('horizontal_crs'):settings['horizontal_crs']=g['horizontal_crs']
    return settings


def review_settings(project,values,reviewer):
    """Presentation-only review; never alters approved hydraulic configuration."""
    project=safe_path(ROOT,project)
    if not isinstance(values,dict) or not str(reviewer or '').strip():raise ValueError('Named delivery review is required')
    allowed={'horizontal_crs','contour_interval','imagery','terrain_label'}
    if set(values)-allowed:raise ValueError('Unsupported delivery review field')
    result=dict(settings_for(project));result.update(values)
    crs=CRS.from_user_input(result.get('horizontal_crs'))
    if not crs.is_projected:raise ValueError('Use the reviewed projected geometry CRS')
    interval=float(result.get('contour_interval',2))
    if not math.isfinite(interval) or interval<=0:raise ValueError('Contour interval must be positive')
    imagery=result.get('imagery',{})
    if imagery.get('mode')=='usgs_naip':
        if imagery.get('raster'):raise ValueError('Choose USGS imagery or a local raster, not both')
    elif imagery.get('raster'):
        if not safe_path(project.parent,imagery['raster']).is_file():raise ValueError('Imagery file is missing')
        if not str(imagery.get('source','')).strip():raise ValueError('Imagery attribution is required')
    elif imagery.get('mode')!='not_available' or not str(imagery.get('reason','')).strip():
        raise ValueError('Supply imagery and source, or explicitly record why it is unavailable')
    result.update(reviewed=True,reviewer=reviewer.strip(),reviewed_utc=utc(),contour_interval=interval)
    save(project.parent/'delivery.settings.json',result);return result


def config_origin(summary):
    h=summary['hydraulics'];run=(ROOT/h['raw_hdf']['path']).parent.parent
    manifest=read(run/'manifest.json');c=summary['configuration']
    matches=[]
    for e in manifest['source_inputs']:
        p=ROOT/e['path']
        if p.suffix=='.json' and intact([e]):
            try:
                if read(p)==c:matches.append(p)
            except (ValueError,OSError):pass
    if len(matches)!=1:raise ValueError('Run configuration changed or is ambiguous; restore the bound inputs before delivery')
    return matches[0],run,manifest


def seal(folder):
    folder=Path(folder)
    entries=[dict(path=p.relative_to(folder).as_posix(),sha256=sha(p),size_bytes=p.stat().st_size)
             for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='PACKAGE_MANIFEST.json']
    save(folder/'PACKAGE_MANIFEST.json',dict(schema_version=SCHEMA,files=entries,total_bytes=sum(e['size_bytes'] for e in entries)))
    return dict(path=rel(folder),files=len(entries)+1,content_bytes=sum(e['size_bytes'] for e in entries),manifest=item(folder/'PACKAGE_MANIFEST.json'))


def verify(folder):
    folder=safe_path(ROOT,folder);m=read(folder/'PACKAGE_MANIFEST.json')
    if m.get('schema_version')!=SCHEMA:raise ValueError('Unsupported delivery manifest')
    names=set()
    for e in m['files']:
        raw=folder/e['path'];p=raw.resolve()
        if not p.is_relative_to(folder) or raw.is_symlink() or not p.is_file():raise ValueError('Missing or unsafe package file: '+e['path'])
        if e['path'].casefold() in names:raise ValueError('Duplicate package entry')
        names.add(e['path'].casefold())
        if p.stat().st_size!=e['size_bytes'] or sha(p)!=e['sha256']:raise ValueError('Package file changed: '+e['path'])
    actual={p.relative_to(folder).as_posix().casefold() for p in folder.rglob('*') if p.is_file() and p.name!='PACKAGE_MANIFEST.json'}
    if actual!=names:raise ValueError('Unlisted files in package; use a separate copy for recomputation')
    refs=spatial.check_references(folder)
    return dict(status='VERIFIED',files=len(m['files']),dependencies=refs,
        scope='Bytes and native references; does not imply GUI reopening, hydraulic QA or design acceptance')


def copy_file(source,destination):
    source=Path(source);destination=Path(destination)
    if not source.is_file() or source.is_symlink():raise ValueError('Missing/unsafe delivery source: '+str(source))
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    if sha(source)!=sha(destination):raise ValueError('Delivery copy mismatch')


def prepare_terrain(raster,crs,bounds,unit,datum,engine,full):
    """Crop actual terrain, convert its vertical unit, then invoke native creation."""
    factor={'m':1/.3048,'US survey foot':(1200/3937)/.3048,'international foot':1}[unit]
    # Imported native ftUS geometry is displayed with the same vertical convention.
    native_unit=engine['native_length_unit'];target_factor=(1200/3937)/.3048 if native_unit=='US survey foot' else 1
    factor/=target_factor
    target=full/'HEC_RAS/Terrain';target.mkdir(parents=True)
    dest=full/'GIS/Terrain_source.tif';projection=full/'CRS/Projection.prj';projection.parent.mkdir()
    projection.write_text(crs.to_wkt(version='WKT1_ESRI'),encoding='utf-8')
    from .map_raster import terrain as project_terrain
    raster_receipt=project_terrain(raster,dest,crs,bounds,factor,datum,native_unit)
    exe=Path(engine['selected']['executable']).parent/'RasProcess.exe';hdf=target/'Terrain.hdf'
    args=[str(exe),'CreateTerrain','units=Feet','stitch=false','prj='+str(projection),'out='+str(hdf),str(dest)]
    r=subprocess.run(args,cwd=target,capture_output=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (full/'Evidence/terrain_creation.log').write_bytes(r.stdout+r.stderr)
    if r.returncode or not hdf.is_file():raise RuntimeError('Native delivery terrain creation failed')
    return hdf,dest,projection,dict(**raster_receipt,
        native_length_unit=native_unit,args=args,executable_sha256=sha(exe))


def associate(project,terrain,engine,log):
    exe=Path(engine['selected']['executable']).parent/'RasProcess.exe';geometry=project.with_suffix('.g01.hdf')
    args=[str(exe),'SetGeometryAssociation','GeometryFilename='+str(geometry),'TerrainFilename='+str(terrain)]
    r=subprocess.run(args,cwd=project.parent,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    Path(log).write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('Native delivery terrain association failed')
    with h5py.File(geometry,'r') as h:
        linked=h['Geometry'].attrs.get('Terrain Filename');linked=linked.decode() if isinstance(linked,bytes) else linked
    if not linked or (geometry.parent/linked).resolve()!=terrain.resolve():raise ValueError('Native terrain association readback mismatch')


def cached_imagery(package,crs,bounds):
    """Reuse only an intact prior NAIP mosaic for the identical map extent."""
    package=safe_path(ROOT,package);verify(package)
    receipt=package/'Evidence/imagery.json';r=read(receipt)
    if r.get('method')=='REUSED_VERIFIED_OFFLINE_MOSAIC':r=r['acquisition']
    if r.get('status')!='READY_FOR_MAP_REVIEW':raise ValueError('Previous imagery has no verified acquisition record')
    if not CRS.from_user_input(r['requested_crs']).equals(crs,ignore_axis_order=True):raise ValueError('Previous imagery CRS differs; acquire imagery for the revised extent')
    tolerance=max(bounds[2]-bounds[0],bounds[3]-bounds[1])*1e-8
    if any(abs(a-b)>tolerance for a,b in zip(bounds,r['requested_bounds'])):raise ValueError('Previous imagery extent differs; acquire imagery for the revised extent')
    raster=package/'GIS/Aerial.tif'
    if not raster.is_file() or sha(raster)!=r['raster']['sha256']:raise ValueError('Previous mosaic differs from its acquisition hash')
    return dict(method='REUSED_VERIFIED_OFFLINE_MOSAIC',acquisition=r,source=r['source'],raster=item(raster),
                previous_receipt=item(receipt),previous_manifest=item(package/'PACKAGE_MANIFEST.json'),network_requests=0)


def generate(summary_path,output,reuse_package=None):
    summary_path=safe_path(ROOT,summary_path);summary=read(summary_path);c=summary['configuration'];h=summary.get('hydraulics')
    if not h:raise ValueError('A verified actual solver run is required for a computed delivery')
    from .report_data import collect
    collect(summary_path)  # Verifies raw solver outputs and the sealed extraction.
    cp,run,run_manifest=config_origin(summary);settings=c.get('delivery',{})
    setting_path=cp.parent/'delivery.settings.json'
    if setting_path.exists():
        settings=read(setting_path)
        if settings.get('reviewed') is not True or not settings.get('reviewer'):
            raise ValueError('Delivery settings require a named review')
    output=safe_path(ROOT,output)
    if output.exists():raise ValueError('Choose a new delivery folder; existing packages are never overwritten')
    if output.is_relative_to(run):raise ValueError('Delivery cannot be nested inside the solver evidence being archived')
    output.mkdir(parents=True);full=output/'Complete';minimal=output/'Minimal';full.mkdir();minimal.mkdir()
    for name in ['HEC_RAS','GIS','Graph','Evidence','Reports','Inputs']:(full/name).mkdir()
    result=dict(schema_version=SCHEMA,status='IN_PROGRESS',created_utc=utc(),summary=item(summary_path),run_id=h['run_id'],
        hydraulic_qa=h['hydraulic_qa_status'],engineering_acceptance='NOT_ASSESSED',input_adequacy=summary['gate']['input_adequacy_status'],
        gui_reopen='NOT_PERFORMED',visual_review='PENDING',cross_machine_validation='NOT_PERFORMED',issues=[])
    save(output/'delivery.json',result)
    try:
        native=(ROOT/h['raw_hdf']['path']).parent
        projects=list(native.glob('*.prj'))
        if len(projects)!=1:raise ValueError('Ambiguous native project')
        source_project=projects[0];project=full/'HEC_RAS'/source_project.name
        for ext in ['.prj','.g01','.f01','.p01','.g01.hdf','.p01.hdf','.O01']:
            copy_file(source_project.with_suffix(ext),project.with_suffix(ext))
        # Verify effective input bytes against the completed run, not just result hashes.
        if not intact(run_manifest['native_after']):raise ValueError('Native inputs changed after computation')
        from .native import discover
        engine=discover()
        if engine['status']!='READY':raise ValueError('Verified HEC-RAS installation is needed to prepare portable terrain')
        copy_file(ROOT/engine['runtime']['path'],project.parent/'msvcr100.dll')
        engine['native_length_unit']=c.get('native_length_unit','international ft')
        from .report_catalog import inspect as editions
        catalog=editions(summary_path)
        if catalog['issues'] or not catalog['latest']:raise ValueError('Latest report evidence requires review: '+str(catalog['issues']))
        report_manifest=ROOT/catalog['latest']['manifest']['path'];rm=catalog['latest']['content']
        for row in rm['reports']:
            for key in ['docx','pdf']:
                e=row[key]
                if not intact([e]):raise ValueError('Report changed after generation')
                copy_file(ROOT/e['path'],full/'Reports'/Path(e['path']).name)
        for key in ['data','figures']:
            if rm.get(key):copy_file(ROOT/rm[key]['path'],full/'Reports'/Path(rm[key]['path']).name)
        figure_dir=report_manifest.parent/'figures'
        if figure_dir.exists():
            for p in figure_dir.iterdir():
                if p.is_file():copy_file(p,full/'Reports/figures'/p.name)
        copy_file(report_manifest,full/'Evidence/report_manifest.original.json')
        copy_file(summary_path,full/'Evidence/summary.original.json')
        if summary.get('native_supplement'):
            from .app_outputs import validate as validate_outputs
            supplement=validate_outputs(summary['native_supplement'])
            copy_file(ROOT/summary['native_supplement']['path'],full/'Evidence/NativeSupplement/bundle.json')
            for i,entry in enumerate(supplement['files']):copy_file(ROOT/entry['path'],full/'Evidence/NativeSupplement'/str(i)/Path(entry['path']).name)
            copy_file(ROOT/supplement['summary']['path'],full/'Evidence/NativeSupplement/source_summary.json')

        save(full/'Evidence/delivery_settings.json',settings)
        from . import __version__
        save(full/'Evidence/delivery_generator.json',dict(version=__version__,created_utc=utc(),
            code=[item(Path(__file__).parent/name) for name in ['site_delivery.py','delivery_spatial.py','qgis_runtime.py','qgis_delivery_worker.py','map_raster.py','imagery.py']]))
        copy_file(run/'manifest.json',full/'Evidence/run_manifest.original.json')
        # Preserve exact input snapshots; original paths in logs are historical locators.
        total=0;limit=int(settings.get('max_complete_bytes',1_500_000_000))
        for e in run_manifest['input_snapshots']:
            if not intact([e]):raise ValueError('Input snapshot changed')
            total+=e['size_bytes']
            if total>limit:raise ValueError('Complete-package input budget exceeded; review the selection')
            source=ROOT/e['path'];relative=source.relative_to(run/'inputs_before')
            copy_file(source,full/'Inputs'/relative)
        for p in run.iterdir():
            if p.is_file() and p.suffix.lower() in ['.json','.txt','.log']:copy_file(p,full/'Evidence/Run'/p.name)
        for p in native.iterdir():
            if p.is_file() and p.suffix.lower() in ['.log','.txt','.json']:copy_file(p,full/'Evidence/Run/Native'/p.name)
        for entry in settings.get('additional_sources',[]):
            source=safe_path(cp.parent,entry)
            total+=source.stat().st_size
            if total>limit:raise ValueError('Complete-package source budget exceeded')
            copy_file(source,full/'Sources'/source.relative_to(ROOT))
        mapped=False;terrain_config=c.get('terrain',{})
        if terrain_config.get('mode')=='not_applicable' or settings.get('mapping_enabled',True) is False:
            result['issues'].append('Mapping not requested or no reviewed georeferenced terrain; native-only packages, no Mapper/GIS exhibit claimed.')
        else:
            geometry=read(safe_path(cp.parent,c['geometry'])) if c.get('geometry') else {}
            crs_value=settings.get('horizontal_crs') or geometry.get('horizontal_crs')
            if not crs_value:raise ValueError('Delivery needs a reviewed geometry horizontal_crs')
            crs=CRS.from_user_input(crs_value);data=spatial.extract(ROOT/h['raw_hdf']['path'],crs)
            bounds=data['bounds'];margin=float(settings.get('map_margin_fraction',.08))
            if not 0<=margin<=.5:raise ValueError('map_margin_fraction must be between 0 and 0.5')
            padx=(bounds[2]-bounds[0])*margin;pady=(bounds[3]-bounds[1])*margin
            bounds=[bounds[0]-padx,bounds[1]-pady,bounds[2]+padx,bounds[3]+pady]
            # Both print maps are square. Crop for their actual display extent,
            # not only the narrower XS envelope (which would leave blank bands).
            cx=(bounds[0]+bounds[2])/2;cy=(bounds[1]+bounds[3])/2
            radius=max(bounds[2]-bounds[0],bounds[3]-bounds[1])/2
            bounds=[cx-radius,cy-radius,cx+radius,cy+radius]
            raster=terrain_config.get('raster')
            if not raster:raise ValueError('Review and apply the acquired terrain raster before Mapper delivery')
            raster=safe_path(cp.parent,raster);unit=terrain_config['vertical_unit'];datum=terrain_config['vertical_datum']
            terrain,dem,projection,terrain_receipt=prepare_terrain(raster,crs,bounds,unit,datum,engine,full)
            save(full/'Evidence/terrain.json',terrain_receipt);save(full/'Evidence/native_spatial.json',data)
            associate(project,terrain,engine,full/'Evidence/terrain_association.log')
            image_settings=settings.get('imagery',{});image=None
            if image_settings.get('mode')=='usgs_naip':
                if reuse_package:
                    acquired=cached_imagery(reuse_package,crs,bounds)
                else:
                    from .imagery import acquire as acquire_imagery
                    acquired=acquire_imagery(crs,bounds,full/'Evidence/Imagery',
                        image_settings.get('max_download_bytes',40_000_000),image_settings.get('max_pixels',1600))
                image=full/'GIS/Aerial.tif';copy_file(ROOT/acquired['raster']['path'],image)
                image_settings=dict(image_settings,source=acquired['source'])
                save(full/'Evidence/imagery.json',acquired)
            elif image_settings.get('raster'):
                image_source=safe_path(cp.parent,image_settings['raster'])
                if not str(image_settings.get('source','')).strip():raise ValueError('Offline imagery needs a source/attribution')
                with rasterio.open(image_source) as ds:
                    if not horizontal_crs(ds.crs.to_wkt()).equals(crs,ignore_axis_order=True):raise ValueError('Reproject imagery to the reviewed map CRS before delivery')
                    if ds.count<3:raise ValueError('Reviewed aerial imagery requires RGB bands')
                    b=ds.bounds
                    if not (b.left<=bounds[0] and b.bottom<=bounds[1] and b.right>=bounds[2] and b.top>=bounds[3]):raise ValueError('Imagery does not cover the map extent')
                image=full/'GIS/Aerial.tif';copy_file(image_source,image)
                save(full/'Evidence/imagery.json',dict(source=item(image_source),attribution=image_settings['source']))
            elif image_settings.get('mode')!='not_available' or not image_settings.get('reason'):
                raise ValueError('Offline imagery missing: supply a reviewed raster/source or explicitly record imagery not_available with a reason')
            else:result['issues'].append('Imagery unavailable: '+image_settings['reason'])
            interval=float(settings.get('contour_interval',2))
            if not math.isfinite(interval) or interval<=0:raise ValueError('Contour interval must be positive')
            unit_label='ftUS' if engine['native_length_unit']=='US survey foot' else 'ft'
            axis=crs.axis_info[0];horizontal_label='ftUS' if abs(axis.unit_conversion_factor-1200/3937)<1e-10 else 'ft' if abs(axis.unit_conversion_factor-.3048)<1e-10 else axis.unit_name
            request=dict(output=str(full),title=c['title'],crs=crs.to_wkt(),crs_label=crs.to_authority() and ':'.join(crs.to_authority()) or crs.name,
                dem=str(dem),imagery=str(image) if image else None,spatial=data,bounds=bounds,contour_interval=interval,
                horizontal_unit_label=horizontal_label,vertical_unit_label=unit_label,vertical_datum=datum,
                terrain_label=settings.get('terrain_label','Reviewed terrain; see Evidence/terrain.json'),
                imagery_label=image_settings.get('source',image_settings.get('reason','Imagery unavailable')),
                flow_label='; '.join(f"{p['profile_id']}: {p['flow_cfs']:g} cfs" for p in h['profiles']),run_id=h['run_id'],
                date=__import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo('America/Los_Angeles')).strftime('%d %b %Y').upper())
            save(output/'qgis_request.json',request)
            from .qgis_runtime import run as qgis_run
            qgis_run(output/'qgis_request.json',output)
            spatial.mapper(project,terrain,projection,bounds,interval,image,full/'GIS/Contours.shp')
            mapped=True
        for directory in ['HEC_RAS','CRS']:
            if (full/directory).exists():shutil.copytree(full/directory,minimal/directory)
        if mapped:
            for p in (full/'GIS').glob('Contours.*'):copy_file(p,minimal/'GIS'/p.name)
            if (full/'GIS/Aerial.tif').exists():copy_file(full/'GIS/Aerial.tif',minimal/'GIS/Aerial.tif')
            copy_file(full/'Graph/Exhibit_EN.pdf',minimal/'Graph/Exhibit_EN.pdf')
        text=(f"{c['title']}\n\nENGLISH\nRun: {h['run_id']}\nOpen HEC_RAS/{project.name} in HEC-RAS 7.0.1. "
            +('Enter RAS Mapper for terrain, sections and ground contours. Enable Offline imagery and Ground contours together for the aerial view.\nOpen Graph/Exhibit_EN.pdf for the exhibit.\n' if mapped else 'This native-only package has no reviewed map or terrain.\n')
            +'Keep all subfolders together. The complete package additionally contains editable GIS_Project.qgz (when mapped), English/Chinese reports, inputs and evidence.\n'
            +f"Input adequacy: {result['input_adequacy']}. Hydraulic QA: {result['hydraulic_qa']}. Engineering acceptance: NOT_ASSESSED.\n"
            +'For recomputation, copy the folder first. Open the saved plan in Steady Flow Analysis and Compute; review warnings. Recalculation creates additional files.\n'
            +'Evidence records retain original workspace paths as historical provenance; copied inputs are under Inputs with their original relative structure.\n\n'
            +'简体中文\n用 HEC-RAS 7.0.1 打开 HEC_RAS 下的工程；有地图时进入 RAS Mapper。Graph 为展示 PDF；完整包另含可编辑 GIS、详细报告、输入及证据。\n'
            +'保持目录完整。重新计算前先复制文件夹，再打开恒定流方案计算并复核警告。结构参数仍为条件性资料，水力 QA 待复核，不能据此认定设计合格。\n'
            +'两个包来自同一个运行。地图是地形和模型位置展示，不是已验证的洪泛范围。\n')
        for folder in [full,minimal]:(folder/'READ_ME.txt').write_text(text,encoding='utf-8-sig')
        comparison=('PACKAGE COMPARISON / 交付包比较\n\nBoth: native inputs/results, runtime, opening instructions; when mapped: Terrain, CRS, offline imagery (if available), contour SHP and English exhibit.\n'
            'Complete only: editable QGIS project/layouts, English/Chinese exhibits, detailed bilingual DOCX/PDF reports, original input snapshots and run/QA evidence.\n'
            '最小包用于打开模型、Mapper 和查看英文展示图；完整包额外用于详细技术复核、核查输入依据及编辑制图。\n'
            'The receiving engineer can compare both packages and request any additional supporting files.\n')
        (output/'PACKAGE_COMPARISON.txt').write_text(comparison,encoding='utf-8-sig')
        for folder in [full,minimal]:spatial.check_references(folder)
        result.update(status='READY_FOR_REVIEW' if mapped else 'READY_NATIVE_ONLY',mapped=mapped,
            complete=seal(full),minimal=seal(minimal),validation_scope='Verified bytes, native terrain association, QGIS save/reopen and exports; desktop/visual review separate')
        verify(full);verify(minimal);save(output/'delivery.json',result)
        register(summary_path,output/'delivery.json')
    except Exception as e:
        result.update(status='INCOMPLETE',error=str(e));save(output/'delivery.json',result)
        raise
    return result
