"""External geometry sensitivity drafts sampled from the declared real DEM.

No automatic promotion into a site's authorised model. Buried geometry and
roadway inputs remain identical; new banks/flow paths are explicitly inferred.
"""
import copy
import math

import numpy as np
import rasterio
from pyproj import CRS, Transformer

from .common import ROOT, finite, item, read, rel, safe_path, save, utc
from .inputs import geometry_errors, load
from .sections import intersect

VERTICAL_FACTORS = {'m': 1/.3048, 'international foot': 1.,
                    'US survey foot': (1200/3937)/.3048}


def plot_review(original, variant, raster, folder, vertical_unit):
    """Actual DEM and cutlines; review artifact, not an inundation map."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from rasterio.windows import from_bounds
    cuts = np.asarray([r['cutline_xy'] for r in variant['cross_sections']]).reshape(-1, 2)
    lo = cuts.min(axis=0)-80; hi = cuts.max(axis=0)+80
    with rasterio.open(raster) as d:
        window = from_bounds(lo[0], lo[1], hi[0], hi[1], d.transform).round_offsets().round_lengths()
        data = d.read(1, window=window, masked=True, boundless=True)
        bounds = rasterio.windows.bounds(window, d.transform)
        resolution = d.res[0]
    origin = np.floor(lo/1000)*1000
    fig, ax = plt.subplots(figsize=(8, 8))
    dem = data.filled(np.nan)
    shade = LightSource(315, 45).hillshade(np.nan_to_num(dem, nan=float(np.nanmedian(dem))),
                                          dx=resolution, dy=resolution)
    extent = [bounds[0]-origin[0], bounds[2]-origin[0], bounds[1]-origin[1], bounds[3]-origin[1]]
    ax.imshow(shade, extent=extent, cmap='gray', vmin=0, vmax=1, alpha=.85)
    for records, colour, label, width in [(original['cross_sections'], '#ed8a23', 'Baseline sections', 1.7),
                                         (variant['cross_sections'], '#007da5', 'Sensitivity draft', .8)]:
        for i, row in enumerate(records):
            cut = np.asarray(row['cutline_xy'])-origin
            ax.plot(cut[:, 0], cut[:, 1], color=colour, lw=width, label=label if i==0 else None)
    centers = np.asarray([r['center_xy'] for r in variant['cross_sections']])-origin
    ax.plot(centers[:, 0], centers[:, 1], color='#c12468', lw=.8, ls='--', label='Effective 1D path')
    for row in variant['cross_sections']:
        if row['rs'] in [variant['structure']['us_xs_rs'], variant['structure']['ds_xs_rs']]:
            x, y = np.asarray(row['center_xy'])-origin
            ax.annotate('Face '+str(row['rs']), (x, y), xytext=(15, 0), textcoords='offset points', fontsize=8)
    crs = CRS.from_user_input(variant['horizontal_crs']); unit = crs.axis_info[0].unit_name
    ax.set(xlabel=f'Easting ({unit}); origin {origin[0]:.0f}', ylabel=f'Northing ({unit}); origin {origin[1]:.0f}',
           title=variant['sensitivity']['spec']['id']+' | External geometry review', aspect='equal')
    ax.legend(loc='upper left', fontsize=8)
    ax.annotate('N', xy=(.94, .93), xytext=(.94, .85), xycoords='axes fraction', ha='center',
                arrowprops=dict(arrowstyle='->'))
    length = 100*.3048/crs.axis_info[0].unit_conversion_factor
    x = bounds[0]-origin[0]+35; y = bounds[1]-origin[1]+35
    ax.plot([x, x+length], [y, y], color='black', lw=3); ax.text(x, y+12, '100 international ft', fontsize=7)
    fig.text(.08, .02, f'DEM: {rel(raster)} | {variant["vertical_datum"]}, {vertical_unit}\n'
             f'{crs.to_string()} | {utc()[:10]} | Draft flow paths/banks, not a flood map', fontsize=7)
    fig.tight_layout(rect=[0, .065, 1, 1])
    target=folder/'geometry_review.png'; fig.savefig(target, dpi=160); plt.close(fig)
    return item(target, 'actual_DEM_geometry_review')


def transform(g, spec, sample, xy_to_ft):
    """Pure transformation with an explicit DEM sampler; returns a draft copy."""
    result = copy.deepcopy(g); xs = result['cross_sections']; s = result['structure']
    ui = next(i for i, r in enumerate(xs) if r['rs'] == s['us_xs_rs']); di = ui + 1
    kind = spec['type']; changes = []
    if kind in ['width_extension','spacing_refinement','domain_extension'] and any(r.get(k) for r in xs for k in ['manning_segments','ineffective_left','ineffective_right']):
        raise ValueError('Automatic geometry sensitivity cannot interpolate reviewed Manning subdivisions or ineffective areas. Create and review the revised sections in the geometry wizard; these fields must not be copied to new stations silently.')

    def positive(name):
        value = spec.get(name)
        if not finite(value) or value <= 0:
            raise ValueError('Explicit positive value required: ' + name)
        return value

    def sampled(template, cut, center, rs, banks):
        row = copy.deepcopy(template); old = np.asarray(template['cutline_xy'])
        if len(old) != 2:
            raise ValueError('Sensitivity adapter requires straight two-point cutlines')
        # Native data checker requires each bank to be an explicit Sta/Elev point.
        # Sample those locations from DEM rather than snapping the inferred bank.
        station_map = {round(v, 3): v for v in row['station_ft']}
        station_map.update({round(float(v), 3): float(v) for v in banks})
        stations = np.asarray(sorted(station_map.values()))
        if len(stations) > 500:
            raise ValueError('Sensitivity section exceeds the adapter 500-point limit')
        fractions = (stations - stations[0])/(stations[-1] - stations[0])
        points = cut[0] + fractions[:, None]*(cut[1] - cut[0])
        row.update(rs=round(rs, 2), center_xy=np.asarray(center).tolist(), cutline_xy=cut.tolist(),
                   station_ft=stations.tolist(), elevation_ft=sample(points).tolist(), bank_stations_ft=list(banks),
                   provenance='DEM sampled external sensitivity; bank positions inferred from neighbouring reviewed sections',
                   review_status='DRAFT_CONDITIONAL_SENSITIVITY')
        return row

    if kind == 'width_extension':
        extra = positive('each_side_ft'); step = positive('sampling_ft')
        # Keep the four original structure sections and their road/barrel coordinates.
        protected = {ui-1, ui, di, di+1}
        for i, row in enumerate(xs):
            if i in protected:
                continue
            stations = np.asarray(row['station_ft']); cut = np.asarray(row['cutline_xy'])
            if len(cut) != 2:
                raise ValueError('Width extension requires straight cutlines')
            n = math.ceil(extra/step)
            new_stations = np.r_[np.linspace(stations[0]-extra, stations[0], n+1)[:-1],
                                 stations, np.linspace(stations[-1], stations[-1]+extra, n+1)[1:]]
            if len(new_stations) > 500:
                raise ValueError('Sensitivity section exceeds the adapter 500-point limit')
            direction = (cut[-1]-cut[0])/(stations[-1]-stations[0])
            outside = np.r_[new_stations[:n], new_stations[-n:]]
            z = sample(cut[0]+(outside-stations[0])[:, None]*direction)
            row['station_ft'] = new_stations.tolist()
            row['elevation_ft'] = np.r_[z[:n], row['elevation_ft'], z[n:]].tolist()
            row['cutline_xy'] = [list(cut[0]-extra*direction), list(cut[-1]+extra*direction)]
            changes.append(dict(station=row['rs'], added_points=2*n, original_points_preserved=True))
    elif kind == 'spacing_refinement':
        maximum = positive('max_spacing_ft'); refined = []
        for i, row in enumerate(xs[:-1]):
            nxt = xs[i+1]; parts = 1 if i == ui else math.ceil(row['reach_lengths_ft'][1]/maximum)
            lengths = [v/parts for v in row['reach_lengths_ft']]
            original = copy.deepcopy(row); original['reach_lengths_ft'] = lengths
            refined.append(original)
            for k in range(1, parts):
                f = k/parts
                cut = (1-f)*np.asarray(row['cutline_xy']) + f*np.asarray(nxt['cutline_xy'])
                center = (1-f)*np.asarray(row['center_xy']) + f*np.asarray(nxt['center_xy'])
                banks = (1-f)*np.asarray(row['bank_stations_ft']) + f*np.asarray(nxt['bank_stations_ft'])
                new = sampled(row, cut, center, (1-f)*row['rs']+f*nxt['rs'], banks)
                new['reach_lengths_ft'] = lengths; refined.append(new)
                changes.append(dict(station=new['rs'], bracket=[row['rs'], nxt['rs']],
                                    method='Interpolate cutline and bank positions; sample elevations directly from DEM'))
        refined.append(xs[-1]); result['cross_sections'] = refined
    elif kind == 'domain_extension':
        distance = positive('each_end_ft'); step = positive('max_spacing_ft')
        parts = math.ceil(distance/step); step = distance/parts
        first, last = xs[0], xs[-1]
        directions = [np.asarray(first['center_xy'])-xs[1]['center_xy'],
                      np.asarray(last['center_xy'])-xs[-2]['center_xy']]
        directions = [v/np.linalg.norm(v) for v in directions]
        ends = []
        for side, template, direction in zip(['upstream', 'downstream'], [first, last], directions):
            new_rows = []
            for k in range(1, parts+1):
                offset = direction*k*step/xy_to_ft
                new = sampled(template, np.asarray(template['cutline_xy'])+offset,
                              np.asarray(template['center_xy'])+offset,
                              template['rs']+(1 if side=='upstream' else -1)*k*step,
                              template['bank_stations_ft'])
                new['reach_lengths_ft'] = [step]*3; new_rows.append(new)
                changes.append(dict(station=new['rs'], side=side,
                                    method='Extrapolated endpoint alignment; actual DEM elevations; copied inferred bank positions'))
            ends.append(new_rows)
        xs[-1]['reach_lengths_ft'] = [step]*3
        ends[1][-1]['reach_lengths_ft'] = [0, 0, 0]
        result['cross_sections'] = ends[0][::-1]+xs+ends[1]
    elif kind == 'boundary_from_sections':
        side = spec.get('side'); n = spec.get('intervals')
        if side not in ['upstream', 'downstream'] or not isinstance(n, int) or not 1 <= n < len(xs):
            raise ValueError('Explicit boundary side and valid interval count required')
        selected = xs[:n+1] if side == 'upstream' else xs[-n-1:]
        if any(s['ds_xs_rs'] <= r['rs'] <= s['us_xs_rs'] for r in selected):
            raise ValueError('Boundary slope support must not include the structure reach')
        def bed(row):
            a = np.asarray(row['station_ft']); z = np.asarray(row['elevation_ft']); left, right = row['bank_stations_ft']
            return float(z[(a >= left) & (a <= right)].min())
        support = sum(r['reach_lengths_ft'][1] for r in selected[:-1])
        slope = (bed(selected[0])-bed(selected[-1]))/support
        if not finite(slope) or slope <= 0:
            raise ValueError('Terrain-derived boundary slope is nonpositive; review the boundary')
        result['boundary_slopes'][side] = slope
        changes.append(dict(side=side, stations=[r['rs'] for r in selected], support_ft=support,
                            end_beds_ft=[bed(selected[0]), bed(selected[-1])], slope=slope,
                            method='Minimum elevation within existing bank stations / actual channel reach lengths'))
    else:
        raise ValueError('Unsupported geometry sensitivity type')
    if result['structure'] != g['structure']:
        raise ValueError('External geometry sensitivity must not alter the structure')
    return result, changes


def prepare(project_path, spec_path, output):
    path, c = load(project_path); spec_path = safe_path(ROOT, spec_path); spec = read(spec_path)
    if not spec.get('purpose') or not spec.get('basis'):
        raise ValueError('Sensitivity purpose and basis required')
    gp = safe_path(path.parent, c['geometry']); g = read(gp); t = c['terrain']
    if t.get('mode') != 'local' or t.get('vertical_unit') not in VERTICAL_FACTORS:
        raise ValueError('Reviewed local DEM with explicit vertical units required')
    if t.get('vertical_datum') != g['vertical_datum']:
        raise ValueError('DEM and geometry datum must match; no assumed vertical offset')
    raster = safe_path(path.parent, t['raster'])
    with rasterio.open(raster) as dem:
        crs = CRS.from_wkt(dem.crs.to_wkt()); crs = crs.sub_crs_list[0] if crs.is_compound else crs
        if not crs.is_projected or not crs.equals(CRS.from_user_input(g['horizontal_crs'])):
            raise ValueError('DEM and geometry horizontal CRS mismatch')
        def sample(points):
            a = np.ma.vstack(list(dem.sample(points, masked=True)))[:, 0]
            if np.ma.getmaskarray(a).any() or not np.isfinite(a.data).all():
                raise ValueError('Sensitivity intersects NoData; no invented terrain')
            return a.data.astype(float)*VERTICAL_FACTORS[t['vertical_unit']]
        variant, changes = transform(g, spec, sample, crs.axis_info[0].unit_conversion_factor/.3048)
    errors = geometry_errors(variant)
    cuts = [np.asarray(r['cutline_xy']) for r in variant['cross_sections']]
    crosses = [(variant['cross_sections'][i]['rs'], variant['cross_sections'][j]['rs'])
               for i in range(len(cuts)) for j in range(i+1, len(cuts)) if intersect(*cuts[i], *cuts[j])]
    if errors or crosses:
        raise ValueError('Sensitivity geometry invalid: ' + repr(dict(errors=errors, intersecting_cutlines=crosses)))
    folder = safe_path(ROOT, output); folder.mkdir(parents=True, exist_ok=False)
    provenance = [item(path), item(gp), item(spec_path), item(raster)]
    variant['provenance'] += provenance
    variant['limitations'] += ['External sensitivity draft; extrapolated/interpolated flow paths and banks need review',
                               'Same road and buried geometry; no structure accuracy improvement implied']
    variant['sensitivity'] = dict(spec=spec, changes=changes, review_status='DRAFT_REQUIRES_REVIEW')
    save(folder/'geometry.json', variant)
    plot = plot_review(g, variant, raster, folder, t['vertical_unit'])
    save(folder/'change_manifest.json', dict(created_utc=utc(), status='DRAFT_REQUIRES_REVIEW',
         sources=provenance, result=item(folder/'geometry.json'), changes=changes,
         review_map=plot,
         original_xs=len(g['cross_sections']), variant_xs=len(variant['cross_sections']),
         structure_unchanged=True, engineering_acceptance='NOT_ASSESSED'))
    tr = Transformer.from_crs(crs, 4326, always_xy=True)
    features = [dict(type='Feature', properties=dict(rs=r['rs'], status='DRAFT_REQUIRES_REVIEW'),
                    geometry=dict(type='LineString', coordinates=[list(tr.transform(*p)) for p in r['cutline_xy']]))
                for r in variant['cross_sections']]
    save(folder/'cutlines.geojson', dict(type='FeatureCollection', features=features))
    (folder/'REVIEW.md').write_text('External geometry sensitivity draft\n\nNo project configuration or authorisation was created. '
        'Review the cutlines, inferred banks and flow paths, boundary support, and unchanged structural inputs before using this geometry. '
        'The original site geometry was not modified. See change_manifest.json for all source hashes.\n', encoding='utf-8')
    return folder
