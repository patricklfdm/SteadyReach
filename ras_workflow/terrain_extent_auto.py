"""Plan terrain coverage and retain the original grid when extending the study area."""
import math

from pyproj import CRS
from rasterio.warp import transform_bounds

from .common import ROOT, finite, read, intact
from .terrain import bbox_for


def plan(model, geometry, config, info, maximum=800., length=400.):
    if not finite(maximum) or not 120 <= maximum <= 2000 or not finite(length) or not 100 <= length <= 1000:
        raise ValueError('Invalid automatic geometry width/reach bounds')
    crs = CRS.from_user_input(info['crs'])
    if not crs.is_projected:
        raise ValueError('Projected DEM required for automatic extent planning')
    rows = geometry.get('cross_sections', [])
    if rows and not crs.equals(CRS.from_user_input(geometry['horizontal_crs'])):
        raise ValueError('Geometry and DEM coordinates differ; review before expanding')
    factor = crs.axis_info[0].unit_conversion_factor/.3048
    if rows:
        points = [p for row in rows for p in row['cutline_xy']]
        # QA extensions can be asymmetric. Existing cutlines plus the full width
        # bound safely cover the permitted search; they do not move the reach.
        padding = maximum/factor
    else:
        kinds = ('river',) if model.get('model_type') == 'river' else ('upstream', 'downstream', 'inlet', 'outlet', 'road')
        points = [p for kind in kinds for p in model.get('map_picks', {}).get(kind, [])]
        if not points and kinds==('river',) and model.get('public_reach') and intact([model['public_reach']]):
            from pyproj import Transformer
            candidate=read(ROOT/model['public_reach']['path'])
            choices=candidate.get('options',[candidate]) if candidate.get('status') in ('CANDIDATE','CHOOSE_REACH') else []
            converter=Transformer.from_crs(4326,crs,always_xy=True)
            points=[converter.transform(*p) for choice in choices for p in choice['anchor_lonlat']]
        if not points:
            return dict(status='NO_EXPLICIT_EXTENT', new_download_bytes=0)
        padding = (maximum/2 + (40. if model.get('model_type') == 'river' else length))/factor
    if any(len(p) != 2 or not all(finite(v) for v in p) for p in points):
        raise ValueError('Finite geometry coordinates required')
    padding += 2*max(info['resolution'])
    required = [min(p[0] for p in points)-padding, min(p[1] for p in points)-padding,
                max(p[0] for p in points)+padding, max(p[1] for p in points)+padding]
    def covers(bounds):
        return bounds[0] <= required[0] and bounds[1] <= required[1] and bounds[2] >= required[2] and bounds[3] >= required[3]
    result = dict(required_bounds=required, horizontal_crs=crs.to_string(), padding_native_units=padding,
                  maximum_width_ft=maximum, maximum_radius_m=2000, maximum_cells=16_000_000,
                  new_download_bytes=0, geometry_changed=False)
    if covers(info['bounds']):
        return dict(result, status='ALREADY_COVERED')
    loc = config.get('location') or {}
    if not all(finite(loc.get(k)) for k in ('latitude','longitude')):
        return dict(result, status='UNAVAILABLE', reason='SITE_LOCATION_REQUIRED')
    for radius in range(50, 2001, 50):
        bounds = transform_bounds(4326, crs, *bbox_for(loc['latitude'],loc['longitude'],radius), densify_pts=21)
        if covers(bounds):
            union = [min(bounds[0],info['bounds'][0]),min(bounds[1],info['bounds'][1]),
                     max(bounds[2],info['bounds'][2]),max(bounds[3],info['bounds'][3])]
            cells = (math.ceil((union[2]-union[0])/info['resolution'][0])+2)*(math.ceil((union[3]-union[1])/info['resolution'][1])+2)
            if cells > result['maximum_cells']:
                return dict(result, status='UNAVAILABLE', reason='AUTOMATIC_CELL_LIMIT', estimated_cells=cells)
            return dict(result, status='EXPANSION_NEEDED', buffer_m=radius, estimated_cells=cells)
    return dict(result, status='UNAVAILABLE', reason='AUTOMATIC_RADIUS_LIMIT')


def ensure(model, options=None):
    from . import app_terrain_extent, geometry_editor
    options = options or {}
    try:
        _,_,_,_,config,geometry,_,terrain,info = geometry_editor.context(ROOT/model['session'])
        request = plan(model,geometry,config,info,
                       options.get('maximum_width_ft',1200. if geometry['cross_sections'] else 800.),
                       options.get('reach_length_ft',400.))
        if request['status'] != 'EXPANSION_NEEDED':
            return request
        if terrain['raster']['sha256'] != model.get('terrain',{}).get('raster',{}).get('sha256'):
            return dict(request,status='UNAVAILABLE',reason='DRAFT_TERRAIN_DIFFERS')
        old = model['terrain']['raster']
        updated = app_terrain_extent.expand_model(model,dict(revision=model['revision'],buffer_m=request['buffer_m']),
                                                 maximum_cells=request['maximum_cells'],allow_download=True)
        return dict(request,status='EXPANDED',previous_raster=old,raster=updated['terrain']['raster'],
                    new_download_bytes=updated['terrain'].get('expansion',{}).get('new_download_bytes',0),
                    acquisition=updated['terrain'].get('expansion'),old_cells_preserved=True)
    except (ValueError, OSError, KeyError) as error:
        # A failed acquisition can transfer bytes before a raster is adopted.
        return dict(status='UNAVAILABLE',reason='CACHED_EXPANSION_UNAVAILABLE',error=str(error),
                    new_download_bytes=getattr(error,'new_download_bytes',0),geometry_changed=False)
