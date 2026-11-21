"""Read-only checks against the requested outputs, before the native solver starts."""
import shutil
from .common import ROOT, safe_path
from .map_raster import horizontal, map_bounds, terrain, terrain_crs


def evaluate(project, config, geometry, mapped, *, raster=None, engine=None):
    from . import native, native_session, qgis_runtime, report_tools
    from rasterio import open as open_raster
    from .river_observations import datum as normalize_datum
    result = {'solver': {'issues': []}, 'reports': {'issues': []}, 'gis': {'issues': []}}
    def issue(group, code, en, zh):
        result[group]['issues'].append(dict(code=code, en=en, zh=zh))

    try:
        engine = native.discover() if engine is None else engine
        if engine.get('status') != 'READY':
            raise ValueError(', '.join(engine.get('blocking_items', [])) or engine.get('error', 'Unavailable'))
        native_session.require_exclusive()
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        issue('solver','ENGINE_UNAVAILABLE','Check or close HEC-RAS. '+str(exc),'请核查 HEC-RAS 安装及打开的工程。'+str(exc))
    try:
        reports = report_tools.discover()
        if reports['blocking_items']:
            raise ValueError(', '.join(reports['blocking_items']))
    except (ValueError, OSError, ImportError) as exc:
        issue('reports','REPORT_TOOLS','Repair the local report tools. '+str(exc),'请修复本机报告工具。'+str(exc))
    settings=config.get('delivery') or {}
    target=settings.get('horizontal_crs') or geometry.get('horizontal_crs')
    metadata=config.get('terrain') or {}
    if mapped:
        try:
            qgis_runtime.environment()
        except (ValueError, OSError) as exc:
            issue('gis','QGIS_TOOLS','Select QGIS in setup. '+str(exc),'请在安装设置中选择 QGIS。'+str(exc))
        try:
            if not target or not horizontal(target).is_projected:
                raise ValueError('A reviewed projected model CRS is required')
            unit,datum=metadata.get('vertical_unit'),metadata.get('vertical_datum')
            if unit not in ('m','US survey foot','international foot') or not datum or str(datum).lower() in ('unknown','unreviewed'):
                raise ValueError('Supply the terrain elevation unit and vertical datum')
            if geometry.get('vertical_datum') and normalize_datum(geometry['vertical_datum'])!=normalize_datum(datum):
                raise ValueError('Model and terrain vertical datums differ')
            path=safe_path(project.parent,metadata['raster']) if metadata.get('raster') else safe_path(ROOT,raster['path']) if raster else None
            if not path or not path.is_file():
                raise ValueError('Supply the reviewed terrain raster')
            points=[xy for section in geometry.get('cross_sections',[]) for xy in section.get('cutline_xy',[])]
            if points:
                x,y=zip(*points)
                bounds=map_bounds((min(x),min(y),max(x),max(y)),settings.get('map_margin_fraction',.08))
                result['gis']['terrain']=terrain(path,None,target,bounds,1,datum,unit)
            else:
                with open_raster(path) as src:
                    terrain_crs(src,horizontal(target))
                result['gis']['extent_pending']=True
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            issue('gis','MAP_TERRAIN','Check the mapped extent, units and CRS. '+str(exc),'请核对地图范围、高程单位及坐标基准。'+str(exc))
    try:
        free=shutil.disk_usage(project.parent).free
        terrain_info=result['gis'].get('terrain',{})
        # Each mapped package includes a Float32 crop. This is an uncompressed
        # working-space estimate, and excludes imagery, logs and other products.
        estimate=8*terrain_info.get('width',0)*terrain_info.get('height',0)
        result['disk']=dict(free_bytes=free,two_terrain_crops_bytes=estimate)
        if free==0:
            issue('solver','DISK_FULL','Free project disk space.','项目磁盘空间已用完。')
        elif estimate>free:
            issue('gis','MAP_DISK','Free space for the two terrain crops.','请为两份地形栅格释放空间。')
    except OSError as exc:
        issue('solver','DISK_UNAVAILABLE','Check the project drive. '+str(exc),'请检查项目所在磁盘。'+str(exc))
    for group in ('solver','reports','gis'):
        row=result[group]
        row['status']='BLOCKED' if row['issues'] else 'NOT_REQUESTED' if group=='gis' and not mapped else 'EXTENT_PENDING' if row.get('extent_pending') else 'CHECKED'
    result['issues']=[entry for group in ('solver','reports','gis') for entry in result[group]['issues']]
    return result


def for_review(model, inputs):
    from .common import read
    path=safe_path(ROOT,model['project'])
    if model.get('native_review'):
        config=read(path)
        meta=model.get('metadata',{})
        config['terrain']=dict(vertical_datum=meta.get('dem_vertical_datum'),vertical_unit=meta.get('dem_vertical_unit'))
        geometry=dict(horizontal_crs=meta.get('horizontal_crs'),vertical_datum=meta.get('vertical_datum'))
    else:
        config,geometry=inputs['configuration'],inputs['geometry']
    return evaluate(path,config,geometry,model['gis'],raster=(model.get('terrain') or {}).get('raster'))
