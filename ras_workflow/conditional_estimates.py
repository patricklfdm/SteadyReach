"""Editable surface-based assumptions with explicit methods and dependencies."""
import math
import numpy as np
from .common import finite
from .app_parameters import proposal
from .app_automation import faces, linear_factor, station, offset, dependency


def continuity_banks(g, index):
    """Bounded end-section extrapolation when two adjacent banks are identifiable."""
    rows=g['cross_sections']
    row=rows[index]
    reach=[i for i,r in enumerate(rows) if r.get('reach_id')==row.get('reach_id')]
    if len(reach)<3 or index not in (reach[0],reach[-1]):
        return None
    neighbors=reach[1:3] if index==reach[0] else reach[-3:-1][::-1]
    near,far=(rows[i] for i in neighbors)
    for section in (row, near, far):
        center=section.get('center_xy') or []
        cutline=section.get('cutline_xy') or []
        x=section.get('station_ft') or []
        z=section.get('elevation_ft') or []
        if len(center)!=2 or not all(finite(v) for v in center):
            return None
        if len(cutline)!=2 or any(len(p)!=2 or not all(finite(v) for v in p) for p in cutline):
            return None
        if len(x)<3 or len(x)!=len(z) or not all(finite(v) for v in x+z):
            return None
        if any(b<=a for a,b in zip(x,x[1:])):
            return None
    if not all(r.get('bank_stations_ft') and len(r.get('cutline_xy',[]))==2 for r in (near,far)):
        return None
    centers=[np.asarray(r['center_xy'],float) for r in (row,near,far)]
    distance=np.linalg.norm(centers[0]-centers[1])
    spacing=np.linalg.norm(centers[1]-centers[2])
    if spacing<=0 or distance>1.5*spacing:
        return None
    def points(section):
        start,end=np.asarray(section['cutline_xy'],float)
        x=section['station_ft']
        return np.array([start+(v-x[0])/(x[-1]-x[0])*(end-start) for v in section['bank_stations_ft']])
    near_xy,far_xy=points(near),points(far)
    projected=near_xy+(near_xy-far_xy)*distance/spacing
    values=[station(row,p) for p in projected]
    x=np.asarray(row['station_ft'],float)
    indices=[int(np.argmin(abs(x-v))) for v in values]
    if not 0<indices[0]<indices[1]<len(x)-1:
        return None
    width=x[indices[1]]-x[indices[0]]
    near_width=near['bank_stations_ft'][1]-near['bank_stations_ft'][0]
    if not .5*near_width<=width<=2*near_width:
        return None
    z=np.asarray(row['elevation_ft'],float)
    bed=float(np.min(z[indices[0]:indices[1]+1]))
    if not np.isfinite(z).all() or min(z[indices])-bed<.5:
        return None
    return dict(method='adjacent_bank_line_extrapolation',selected_indices=indices,evidence_class='assumed',
        confidence='LOW',reasons=['NO_LOCAL_STABLE_BANK_PAIR','ADJACENT_SECTION_BANK_CONTINUITY_ASSUMED'],
        basis='Conditional end-section banks extrapolated from the two nearest same-reach bank lines; extrapolation is bounded to 1.5 section spacings. Local bank breaks are unresolved. Inspect floodplain connectivity and revise these stations if the channel widens or splits.',
        basis_zh='端部断面局部岸线不明确，条件性外推同河段最近两条断面的岸线，距离限定在 1.5 个断面间距内。需核对漫滩连通、河槽变宽或分汊并修改。',
        source_sections=[dict(rs=r['rs'],bank_stations_ft=r['bank_stations_ft'],cutline_xy=r['cutline_xy']) for r in (near,far)],
        projected_xy=projected.tolist(),extrapolation_fraction=float(distance/spacing))


def surface_candidates(m, g, sampler):
    """Use identified mouths and intact DEM. Never label a buried invert surveyed."""
    result = {}
    us, ds = faces(g)
    if not us or not ds:
        return result
    factor = linear_factor(g)
    groups = g['structure']['groups']
    mouths = []
    def valid_point(point):
        return isinstance(point, (list, tuple)) and len(point) == 2 and all(finite(v) for v in point)

    def add(key, value, en, zh, **extra):
        choice = proposal(value, en, zh, 'assumed')
        choice.update(sources=[sampler.source], automation_context=dependency(m,g,key), **extra)
        result[key] = [choice]
    for i, group in enumerate(groups):
        picks = m.get('group_map_picks', {}).get(str(i), {})
        if not picks and len(groups) == 1:
            picks = m.get('map_picks', {})
        if len(picks.get('inlet', [])) != 1 or len(picks.get('outlet', [])) != 1:
            continue
        if not all(valid_point(picks[side][0]) for side in ('inlet','outlet')):
            continue
        inlet, outlet = np.asarray(picks['inlet'][0],float), np.asarray(picks['outlet'][0],float)
        axis = outlet - inlet
        length = np.linalg.norm(axis)
        if length <= 0:
            continue
        axis /= length
        mouths.append((inlet, outlet))
        # Fit exterior surface lows. Separate fits at both mouths avoid assuming a
        # culvert slope equal to the remote boundary slope.
        for side, point, face in [('us', inlet, us), ('ds', outlet, ds)]:
            if not valid_point(face.get('center_xy')):
                continue
            direction = np.asarray(face['center_xy'])-point
            face_distance = np.linalg.norm(direction)*factor
            if face_distance <= max(10., 3*sampler.cell_ft):
                continue
            direction /= np.linalg.norm(direction)
            distances = np.linspace(max(6.6, 2*sampler.cell_ft), face_distance, 12)
            xy = point + distances[:, None]/factor*direction
            bed = sampler.sample(xy)
            if not np.isfinite(bed).all():
                continue
            fits = [np.polyfit(distances[:n], bed[:n], 1) for n in (8, 12)]
            residual = float(np.sqrt(np.mean((np.polyval(fits[-1], distances)-bed)**2)))
            values = [float(f[1]) for f in fits]
            if residual > 1. or max(values)-min(values) > 1.5:
                continue
            add(f'g.structure.groups.{i}.{side}_invert_ft', round(values[-1], 3),
                'Conditional invert from a short exterior DEM profile joining the identified mouth to its exterior section center, excluding the nearest two raster cells. Assumes continuous bed/floor, no buried drop or sediment cover. Datum '+sampler.datum+'. The displayed range compares fit windows and is not a confidence interval.',
                '条件性涵底估计，沿洞口至外侧断面中心的短剖面外推，排除最近两个栅格，假定河床与底板连续且无掩埋跌坎或淤积覆盖。基准 '+sampler.datum+'。范围仅比较拟合窗口。',
                range=sorted(round(v, 3) for v in values), fit=dict(distances_ft=distances.tolist(), sample_xy=xy.tolist(),
                    bed_ft=bed.tolist(), residual_ft=residual, fits=[f.tolist() for f in fits], datum=sampler.datum))
    width = g['structure']['road'].get('width_ft')
    if len(mouths) != len(groups) or not finite(width) or width <= 0:
        return result
    inlet = np.mean([p[0] for p in mouths], axis=0)
    outlet = np.mean([p[1] for p in mouths], axis=0)
    axis = outlet-inlet
    length_ft = np.linalg.norm(axis)*factor
    if not 0 < width < length_ft:
        return result
    axis /= np.linalg.norm(axis)
    normal = np.array([axis[1], -axis[0]])
    # Increasing station is left-to-right looking downstream.
    if np.dot(normal, np.asarray(us['cutline_xy'][-1])-us['cutline_xy'][0]) < 0:
        normal = -normal
    center = (inlet+outlet)/2
    crest_points = m.get('map_picks', {}).get('road', [])
    if len(crest_points) >= 2:
        if not valid_point(crest_points[0]) or not valid_point(crest_points[-1]):
            return result
        a, b = np.asarray(crest_points[0],float), np.asarray(crest_points[-1],float)
        if np.linalg.norm(b-a) < 1e-8:
            return result
        normal = (b-a)/np.linalg.norm(b-a)
        center = (a+b)/2
        axis = np.array([-normal[1], normal[0]])
        if np.dot(axis, outlet-inlet) < 0:
            axis = -axis
    else:
        # Search for a raised, continuous road corridor on both sides of the
        # channel. This is a bounded alignment assumption for visual confirmation.
        if not all(type(b.get('count')) is int and b['count']>0 and finite(b.get('span_ft')) and b['span_ft']>0 for b in groups):
            return result
        span = sum(b['count']*b['span_ft'] for b in groups)
        if span/2+10 >= 90:
            return result
        test_offsets = np.r_[np.linspace(-90, -span/2-10, 16), np.linspace(span/2+10, 90, 16)]
        candidates = []
        for angle in np.linspace(-30, 30, 21):
            radians = math.radians(angle)
            transverse = math.cos(radians)*normal+math.sin(radians)*axis
            along = np.array([-transverse[1], transverse[0]])
            if np.dot(along, axis) < 0:
                along = -along
            for shift in np.linspace(-min(10., length_ft/5), min(10., length_ft/5), 9):
                origin = center+shift/factor*axis
                probes = origin+test_offsets[:, None]/factor*transverse
                levels = sampler.sample(probes)
                if not np.isfinite(levels).all():
                    continue
                candidates.append((float(np.percentile(levels, 20)), -abs(float(angle)), origin, transverse, along))
        if not candidates:
            return result
        best = max(candidates, key=lambda v: v[:2])
        center, normal, axis = best[2:]
    extent = max(r['station_ft'][-1]-r['station_ft'][0] for r in (us, ds))
    lateral = np.linspace(-extent, extent, min(499, math.ceil(2*extent/max(2., sampler.cell_ft))+1))
    built = []
    profiles = []
    for side, face, sign in [('us', us, -1), ('ds', ds, 1)]:
        point = center + sign*width/2/factor*axis
        xy = point + lateral[:, None]/factor*normal
        xx = np.array([station(face, p) for p in xy])
        order = np.argsort(xx)
        xx, xy = xx[order], xy[order]
        if np.any(np.diff(xx) <= 1e-8):
            return result
        z = sampler.sample(xy)
        mask = (xx >= face['station_ft'][0]) & (xx <= face['station_ft'][-1])
        if not mask.any() or not np.isfinite(z[mask]).all():
            return result
        if not all(finite(b.get('span_ft')) and b.get('centers_ft') for b in groups):
            return result
        face_index = 0 if side == 'us' else 1
        if any(not isinstance(p,(list,tuple)) or len(p)!=2 or not all(finite(v) for v in p) for b in groups for p in b['centers_ft']):
            return result
        edges = [(p[face_index]-b['span_ft']/2, p[face_index]+b['span_ft']/2) for b in groups for p in b['centers_ft']]
        left, right = min(p[0] for p in edges), max(p[1] for p in edges)
        # An explicitly labelled bridge-deck assumption over the opening envelope.
        outside = (xx < left-sampler.cell_ft) | (xx > right+sampler.cell_ft)
        outside &= np.isfinite(z)
        crowns = [b.get(('us' if side=='us' else 'ds')+'_invert_ft') for b in groups]
        if all(finite(v) for v in crowns) and all(finite(b.get('rise_ft')) for b in groups):
            crown = max(v+b['rise_ft'] for v, b in zip(crowns, groups))
            left_ids = np.flatnonzero(outside & (xx<left) & (z>crown))
            right_ids = np.flatnonzero(outside & (xx>right) & (z>crown))
            if not len(left_ids) or not len(right_ids):
                return result
            left_shoulder, right_shoulder = xx[left_ids[-1]], xx[right_ids[0]]
            if right_shoulder-left_shoulder > max(3*(right-left), 60.):
                return result
            left, right = left_shoulder+sampler.cell_ft, right_shoulder-sampler.cell_ft
            outside = ((xx<=left_shoulder) | (xx>=right_shoulder)) & np.isfinite(z)
        if not (np.any(outside & (xx < left)) and np.any(outside & (xx > right))):
            return result
        # Interpolation needs real raster coverage at both profile endpoints.
        # Missing exterior samples must not turn into constant extrapolation.
        if xx[outside][0] > face['station_ft'][0] or xx[outside][-1] < face['station_ft'][-1]:
            return result
        target = np.r_[face['station_ft'][0], xx[mask], face['station_ft'][-1]]
        target = np.unique(np.round(target, 3))
        elevations = np.interp(target, xx[outside], z[outside])
        # Keep measured exterior DEM samples outside the bridge span.
        exterior = (target < left-sampler.cell_ft) | (target > right+sampler.cell_ft)
        elevations[exterior] = np.interp(target[exterior], xx, z)
        if not np.isfinite(elevations).all():
            return result
        built.append((target.tolist(), np.round(elevations, 3).tolist(), point))
        profiles.append(dict(side=side, sample_xy=xy.tolist(), station_ft=xx.tolist(),
            sampled_elevation_ft=[float(v) if np.isfinite(v) else None for v in z],
            bridged_station_range_ft=[float(left),float(right)]))
    basis = 'Conditional roadway profiles at the entered width around a mapped crest, or the highest continuous exterior DEM corridor within 30 degrees of the mouth normal and 10 ft of its midpoint. DEM over the opening envelope is bridged linearly between exterior shoulders. Review road alignment, cover and bypass paths.'
    zh = '条件性道路剖面，按已填路宽沿点选路顶采样，或在涵轴垂线 ±30°、中点 ±10 ft 范围寻找连续较高的道路候选。涵孔包络范围内以外侧路肩线性连接，需核对道路方向、顶板覆土和绕流路径。'
    for key, value in [('profile_mode', 'distinct'), ('station_ft', built[0][0]), ('elevation_ft', built[0][1]),
                       ('downstream_station_ft', built[1][0]), ('downstream_elevation_ft', built[1][1]),
                       ('distance_us_ft', round(float(offset(us, built[0][2], factor)), 3))]:
        add('g.structure.road.'+key, value, basis, zh, road_sampling=dict(center_xy=center.tolist(),
            normal_xy=normal.tolist(), axis_xy=axis.tolist(), width_ft=width, mapped_crest=bool(crest_points),
            search_bounds=dict(angle_degrees=30,shift_ft=min(10.,length_ft/5)),profiles=profiles))
    return result


def construction_candidates(m, g, c):
    """A visible baseline scenario, editable before the final run confirmation."""
    result = {}
    for i, group in enumerate(g['structure']['groups']):
        if group.get('shape') != 'box':
            continue
        prefix = f'g.structure.groups.{i}.'
        basis = 'Conditional baseline assumes a continuous concrete floor and square-edged concrete headwall with 90-degree wingwalls. Confirm construction against drawings/photos; change this baseline when unsupported.'
        zh = '条件性基准情景假定连续混凝土底板、直角混凝土端墙入口及 90° 翼墙。请核对图纸／照片并修改不适用的假设。'
        for name, value in [('bottom_type', 'ASSUMED continuous concrete floor'),
                            ('inlet_description', 'ASSUMED square-edged headwall, 90-degree wingwalls'),
                            ('chart_scale', [8, 2]), ('entrance_loss', .5)]:
            result[prefix+name] = [proposal(value, basis, zh)]
    # Manning n stays conditional, with the same material/condition stated.
    if g['structure']['groups'] and all(b.get('shape') == 'box' for b in g['structure']['groups']):
        for index, scenario in enumerate(c.get('scenarios', [])):
            if scenario['id'] == m['scenario']:
                result[f'c.scenarios.{index}.culvert_n'] = [proposal(.013,
                    'Conditional concrete-box baseline, n=0.013. Review floor material, joints and debris; range 0.011–0.014.',
                    '混凝土箱涵条件性基准糙率 0.013；需核对底板、接缝和杂物，参考范围 0.011–0.014。', range_=[.011, .014])]
    return result
