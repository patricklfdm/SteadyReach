"""Construct a single hydraulic change on a copy of a frozen river geometry."""
from copy import deepcopy

import numpy as np
from pyproj import CRS, Transformer

from .common import finite
from .geometry_qa import spatial_issues


def bed(geometry, maximum_ft):
    if not finite(maximum_ft) or maximum_ft == 0:
        raise ValueError('Specify a nonzero signed bed perturbation in ft / 请给出非零的有符号河床变化量')
    result = deepcopy(geometry)
    for row in result['cross_sections']:
        left, right = row['bank_stations_ft']
        if not left < right:
            raise ValueError('Check the bank stations / 请核对岸站')
        t = np.clip((np.asarray(row['station_ft'])-left)/(right-left), 0., 1.)
        row['elevation_ft'] = (np.asarray(row['elevation_ft']) + maximum_ft*4*t*(1-t)).round(5).tolist()
    return result


def outlet(geometry, value, profile_index=0):
    result = deepcopy(geometry)
    b = result['boundaries']['downstream']
    if b.get('type') != 'known_stage' or not finite(value):
        raise ValueError('Use an absolute stage in the datum of an existing known-stage boundary / 请给出已有已知水位边界同基准绝对高程')
    if not 0 <= profile_index < len(b.get('stages_ft', [])):
        raise ValueError('Choose a supported boundary profile / 请核对所选边界工况')
    b['stages_ft'][profile_index] = value
    return result


def surface(geometry, old, new):
    model_crs = CRS.from_user_input(geometry['horizontal_crs'])
    if not model_crs.is_projected or old.datum != geometry['vertical_datum'] or new.datum != old.datum:
        raise ValueError('Check projected geometry and both vertical references / 请核对几何投影及两份地形的垂直基准')
    scale = model_crs.axis_info[0].unit_conversion_factor
    transforms = [Transformer.from_crs(model_crs, s.crs, always_xy=True) for s in (old,new)]
    result = deepcopy(geometry)
    for row in result['cross_sections']:
        cut = np.asarray(row['cutline_xy'],dtype=float)
        chain = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(cut,axis=0),axis=1))]
        distance = (np.array(row['station_ft'])-row['station_ft'][0])*.3048/scale
        if abs(distance[-1]-chain[-1])*scale > .3048 or np.any(np.diff(chain)<=0):
            raise ValueError(f"RS {row['rs']}: section stationing must match the mapped cutline within 1 ft / 请核对断面里程与断面线长度")
        xy = [np.interp(distance,chain,cut[:,k]) for k in (0,1)]
        samples = [s.sample(np.column_stack(tr.transform(*xy,errcheck=True))) for s,tr in zip((old,new),transforms)]
        if any(not np.isfinite(z).all() for z in samples):
            raise ValueError(f"RS {row['rs']}: missing DEM coverage / 缺少 DEM 高程")
        # Add only the elevation difference; keep any existing bed-to-ground offset.
        row['elevation_ft'] = (np.asarray(row['elevation_ft'])+samples[1]-samples[0]).round(5).tolist()
    return result


def nested(geometry, supplied):
    if supplied.get('horizontal_crs') != geometry['horizontal_crs'] or supplied.get('vertical_datum') != geometry['vertical_datum'] or supplied.get('hydraulic_unit')!=geometry['hydraulic_unit']:
        raise ValueError('Nested sections must share horizontal CRS, vertical datum and units / 加密断面须使用同一坐标系、基准和单位')
    rows = supplied.get('cross_sections',[])
    original = geometry['cross_sections']
    if not len(original) < len(rows) <= 500:
        raise ValueError('Supply a refined reach with added sections (up to 500) / 请提供含新增断面的加密河段，最多500条')
    ids = [r['rs'] for r in rows]
    old_ids = [r['rs'] for r in original]
    if ids != sorted(set(ids),reverse=True) or not set(old_ids)<=set(ids) or (ids[0],ids[-1])!=(old_ids[0],old_ids[-1]):
        raise ValueError('Keep the original stations and both ends / 保留原断面和两端')
    # External review metadata may differ. Retain the actual parent rows after checking every hydraulic field.
    metadata = {'terrain_review','review_status','bank_candidates','bank_review','provenance','source','_at'}
    result = deepcopy(geometry)
    new_rows = deepcopy(rows)
    for i,parent in enumerate(original):
        j = ids.index(parent['rs'])
        ignore = metadata | {'reach_lengths_ft'}
        if {k:v for k,v in parent.items() if k not in ignore} != {k:v for k,v in rows[j].items() if k not in ignore}:
            raise ValueError(f"RS {parent['rs']}: original section inputs changed / 原断面参数改变")
        lengths = rows[j]['reach_lengths_ft']
        new_rows[j] = dict(deepcopy(parent),reach_lengths_ft=lengths)
        if i+1<len(original):
            end = ids.index(old_ids[i+1])
            for added in rows[j+1:end]:
                for key in ('reach_id','expansion_contraction','manning_segments','ineffective_left','ineffective_right'):
                    if added.get(key)!=parent.get(key) or (key in ('manning_segments','ineffective_left','ineffective_right') and added.get(key)):
                        raise ValueError(f"RS {added['rs']}: review variable roughness, losses or ineffective areas separately / 请单独复核新增断面的糙率、损失与非有效流区")
            dist = sum(r['reach_lengths_ft'][1] for r in rows[j:end])
            if abs(dist-parent['reach_lengths_ft'][1])>.01:
                raise ValueError(f"RS {parent['rs']}: main-channel length changed / 主槽流程长度改变")
            if end==j+1 and lengths!=parent['reach_lengths_ft']:
                raise ValueError('Unrefined overbank lengths changed / 未加密区间漫滩长度改变')
    if spatial_issues(new_rows):
        raise ValueError('Resolve intersecting or invalid section cutlines / 请先解决断面相交或坐标异常')
    result['cross_sections'] = new_rows
    return result
