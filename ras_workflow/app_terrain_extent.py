"""Expand a draft's DEM from verified cached originals while preserving its old cells."""
import copy
import math

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

from . import app_core as core, geometry_editor as editor, intake
from .common import ROOT, digest, finite, intact, item, lock, read, rel, save, unique_id, utc
from .terrain import bbox_for


def expand_cached(previous, configuration, radius, destination, maximum_cells=None):
    if not finite(radius) or not 50 <= radius <= 5000:
        raise ValueError('Use a DEM radius of 50–5000 m / DEM 范围半径须为 50–5000 米')
    products = previous.get('products', [])
    sources = [p['source'] for p in products]
    if not sources or not intact(sources + [previous['raster']]):
        raise ValueError('Cached USGS originals are missing or changed / 已缓存的 USGS 原始地形缺失或已改变')
    location = configuration['location']
    requested = bbox_for(location['latitude'], location['longitude'], radius)
    with rasterio.open(ROOT / previous['raster']['path']) as old:
        crs = CRS.from_user_input(old.crs).to_2d()
        if not crs.is_projected or old.transform.b or old.transform.d:
            raise ValueError('A north-up projected DEM is required')
        bounds = transform_bounds(4326, crs, *requested, densify_pts=21)
        window = from_bounds(*bounds, old.transform)
        left = min(0, math.floor(window.col_off))
        top = min(0, math.floor(window.row_off))
        right = max(old.width, math.ceil(window.col_off + window.width))
        bottom = max(old.height, math.ceil(window.row_off + window.height))
        width, height = right - left, bottom - top
        if width == old.width and height == old.height:
            raise ValueError('The current DEM already covers this radius / 当前 DEM 已覆盖该半径，请保留现有范围或增大半径')
        if maximum_cells is not None and width*height > maximum_cells:
            raise ValueError("Automatic DEM expansion exceeds the cell limit")
        transform = old.transform * Affine.translation(left, top)
        values = np.full((height, width), np.nan, dtype='float32')
        for product in products:
            with rasterio.open(ROOT / product['source']['path']) as source:
                native = CRS.from_user_input(source.crs).to_2d()
                if native.datum != crs.datum:
                    raise ValueError('Cached DEM datums differ; review source selection')
                additional = np.full_like(values, np.nan)
                reproject(rasterio.band(source, 1), additional,
                          src_transform=source.transform, src_crs=native,
                          src_nodata=source.nodata, dst_transform=transform,
                          dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
                missing = ~np.isfinite(values)
                values[missing] = additional[missing]
        # Keep the previous grid and every old cell, including any old NoData.
        # Existing section samples therefore retain their exact terrain basis.
        original = old.read(1, masked=True).astype('float32').filled(np.nan)
        values[-top:old.height-top, -left:old.width-left] = original
        if not np.isfinite(values).all():
            raise ValueError('Cached originals do not fully cover this radius. Choose a smaller radius or obtain adjoining DEM tiles. / 已缓存原始地形未完整覆盖该范围，请减小半径或补充相邻 DEM 瓦片。')
        profile = old.profile.copy()
        profile.update(width=width, height=height, transform=transform, dtype='float32', nodata=np.nan)
        destination.mkdir(parents=True, exist_ok=True)
        output = destination / 'terrain_aoi.tif'
        with rasterio.open(output, 'w', **profile) as expanded:
            expanded.write(values, 1)
            expanded.update_tags(**old.tags())
        result = copy.deepcopy(previous)
        result.update(raster=item(output, 'working_DEM'), buffer_m=radius,
                      bbox=transform_bounds(crs, 4326, *rasterio.transform.array_bounds(height, width, transform)),
                      valid_fraction=1., nodata_pixels=0, status='READY_EXPLORATORY',
                      expansion=dict(previous_raster=previous['raster'], requested_bbox=requested,
                                     method='Same grid; old cells retained exactly; new cells from cached USGS originals',
                                     new_download_bytes=0, old_cells_preserved=True,
                                     created_utc=utc()))
    save(destination / 'terrain.json', result)
    return result


def expand(key, body):
    model = core.model(key)
    core.require_idle(model)
    expand_model(model, body)
    return core.view(key)


def rebind_preserved_sections(geometry, previous, expanded, unit, datum):
    """Rebind only intact DEM sample records covered by the unchanged old grid."""
    result = copy.deepcopy(geometry)
    rebound = []
    with rasterio.open(ROOT / previous['raster']['path']) as old:
        if (not unit or not datum or not geometry.get('horizontal_crs')
                or not CRS.from_user_input(geometry['horizontal_crs']).equals(CRS.from_user_input(old.crs).to_2d())):
            return result, rebound
        bounds = old.bounds
        for index, row in enumerate(result['cross_sections']):
            stamp = row.get('terrain_sampling') or {}
            fingerprint = digest({k: row.get(k) for k in ('cutline_xy', 'station_ft', 'elevation_ft', 'center_xy')})
            points = row.get('cutline_xy') or []
            if (stamp.get('raster', {}).get('sha256') != previous['raster']['sha256']
                    or stamp.get('spatial_fingerprint') != fingerprint
                    or stamp.get('vertical_unit') != unit or stamp.get('vertical_datum') != datum
                    or not points or any(not (bounds.left <= x <= bounds.right and bounds.bottom <= y <= bounds.top) for x, y in points)):
                continue
            row.setdefault('previous_terrain_sampling', []).append(copy.deepcopy(stamp))
            row['terrain_sampling'] = dict(stamp, raster=expanded['raster'],
                coverage_rebind=dict(method='Cached expansion preserved every original cell',
                                     previous_raster=previous['raster']))
            rebound.append(index)
    return result, rebound


def expand_model(model, body, maximum_cells=None):
    key = model['id']
    if model.get('active_project') or model.get('native_review'):
        raise ValueError('Create an editable revision before expanding terrain')
    if body.get('revision') != model['revision']:
        raise ValueError('Inputs changed; refresh before expanding / 参数已改变，请刷新后扩展')
    sp, _, _, draft, configuration, geometry, terrain_config, current, _ = editor.context(ROOT / model['session'])
    previous = copy.deepcopy(model['terrain'])
    if current['raster']['sha256'] != previous['raster']['sha256']:
        raise ValueError('The draft uses a different DEM; review its terrain source before expansion')
    destination = core.folder(key) / 'preparation' / unique_id() / 'terrain'
    expanded = expand_cached(previous, configuration, body.get('buffer_m'), destination, maximum_cells=maximum_cells)
    rebound_geometry, rebound = rebind_preserved_sections(geometry, previous, expanded,
        model['metadata'].get('dem_vertical_unit'), model['metadata'].get('dem_vertical_datum'))
    checkpoint_path = sp.parent / 'terrain_checkpoint.json'
    checkpoint = read(checkpoint_path) if checkpoint_path.exists() else None
    before = dict(model=model, draft=draft, checkpoint=checkpoint)
    save(destination.parent / 'before.json', before)
    receipt = copy.deepcopy(draft.get('section_workflow', {}))
    receipt.update(terrain=dict(mode='local', raster='terrain_aoi.tif', provenance='terrain.json',
                               vertical_unit=model['metadata'].get('dem_vertical_unit'),
                               vertical_datum=model['metadata'].get('dem_vertical_datum'),
                               create_native=terrain_config.get('create_native', False)),
                   terrain_base=rel(destination), section_count=len(geometry['cross_sections']))
    receipt['sources'] = receipt.get('sources', []) + [previous['raster'], expanded['raster'], item(destination / 'terrain.json')]
    updated_draft = copy.deepcopy(draft)
    updated_draft.update(geometry=rebound_geometry, section_workflow=receipt, consent=False, revision=draft['revision'] + 1)
    receipt['preserved_sample_rebindings'] = rebound
    # Replace only stored terrain path answers that would override the new receipt.
    for field in ('c.terrain.raster', 'c.terrain.provenance'):
        updated_draft['answers'].pop(field, None)
    # Editable revisions may refer directly to a verified local DEM without
    # retaining the original acquisition checkpoint. Keep their explicit
    # metadata; do not manufacture a new product-metadata approval.
    updated_checkpoint = dict(checkpoint or {}, terrain=expanded, created_utc=utc())
    updated_model = copy.deepcopy(model)
    updated_model.update(terrain=expanded, revision=model['revision'] + 1,
                         status='INPUTS_READY', phase='TERRAIN_EXTENT_READY', errors=[])
    with lock(sp.parent / 'session.lock'):
        if read(sp.parent / 'draft.json')['revision'] != draft['revision'] or core.model(key)['revision'] != model['revision']:
            raise ValueError('Inputs changed during expansion; saved inputs retained / 扩展期间输入发生变化，已保留原输入')
        try:
            save(checkpoint_path, updated_checkpoint)
            save(sp.parent / 'draft.json', updated_draft)
            core.persist(updated_model, 'EXPAND_CACHED_DEM', dict(buffer_m=body['buffer_m'], terrain=expanded['raster']))
        except Exception:
            if checkpoint is None:checkpoint_path.unlink(missing_ok=True)
            else:save(checkpoint_path, checkpoint)
            save(sp.parent / 'draft.json', draft)
            save(core.folder(key) / 'app.json', model)
            raise
    return updated_model
