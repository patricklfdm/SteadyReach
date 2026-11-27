"""Locate original USGS Short-Term Network flood marks on the selected river geometry."""
import json
import math
import re
from collections import Counter
from urllib.request import Request, urlopen

import numpy as np
from pyproj import CRS, Transformer

from .river_observations import datum

API = 'https://api.waterdata.usgs.gov/stnservices'
CATALOG = API + '/events/?format=json'
LIMIT = 12_000_000


def event_url(event):
    if type(event) != int or not 0 < event < 1_000_000:
        raise ValueError('Choose a USGS event / 请选择 USGS 事件')
    return f'{API}/hwms/filteredhwms/?event={event}&format=json'


def fetch(url):
    with urlopen(Request(url, headers={'Accept': 'application/json', 'User-Agent': 'SteadyReach'}), timeout=35) as response:
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('USGS response exceeds the file limit / USGS 返回资料超出大小限制')
    return raw


def catalog(raw, year):
    year = str(year)
    if not re.fullmatch(r'[12]\d{3}', year):
        raise ValueError('Enter the four-digit event year / 请填写四位年份')
    return sorted(({'id': r['id'], 'name': r['name'], 'start': r.get('start_date'), 'end': r.get('end_date')}
                   for r in json.loads(raw) if str(r.get('start_date') or '')[:4] <= year <=
                   str(r.get('end_date') or r.get('start_date') or '')[:4] and r.get('start_date')),
                  key=lambda r: (r['start'], r['id']))


def geometry_input(geom):
    paths = [f['xy'] for f in geom.get('flowlines', []) if len(f.get('xy', [])) >= 2]
    cuts = [dict(rs=c['rs'], xy=c['cutline_xy']) for c in geom.get('cross_sections', []) if len(c.get('cutline_xy', [])) >= 2]
    if not paths or len(cuts) < 2 or not geom.get('horizontal_crs'):
        raise ValueError('First save a located centerline, cross sections and their CRS / 请先保存已定位的河线、断面及坐标系')
    crs = CRS.from_user_input(geom['horizontal_crs'])
    if not crs.is_projected:
        raise ValueError('Locate the centerline and cross sections in a projected CRS first / 请先定位投影坐标系下的河线和断面')
    return dict(crs=crs.to_string(), datum=geom.get('vertical_datum'), paths=paths, cuts=cuts)


def segments(line):
    coords = np.asarray(line, dtype=float)
    vectors = np.diff(coords, axis=0)
    squares = np.sum(vectors * vectors, axis=1)
    valid = squares > 0
    if not valid.any() or not np.isfinite(coords).all():
        raise ValueError('Check degenerate reach geometry / 请检查退化的河线或断面')
    return coords[:-1][valid], vectors[valid], squares[valid]


def distance(point, segment):
    start, vectors, squares = segment
    delta = point - start
    t = np.clip(np.sum(delta * vectors, axis=1) / squares, 0., 1.)
    return float(np.min(np.linalg.norm(delta - t[:, None] * vectors, axis=1)))


def crossing_side(row):
    # Site descriptions identify the crossing; a note may say "upstream face of a tree".
    for field in ('site_description', 'location_description'):
        s = (row.get(field) or '').lower()
        upstream = re.search(r'\b(?:upstream|u/s|us)\b', s)
        downstream = re.search(r'\b(?:downstream|d/s|ds)\b', s)
        if upstream or downstream:
            return 'check' if upstream and downstream else 'upstream' if upstream else 'downstream'
    return 'unknown'


def grouped(rows):
    """Same STN site or identical surveyed coordinates within an event constitute at most one location."""
    parents = list(range(len(rows)))
    def root(i):
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    seen = {}
    for i, row in enumerate(rows):
        keys = [('xy', tuple(row['lonlat']))]
        if row['site']:
            keys.append(('site', row['site']))
        for kind, value in keys:
            key = (row['event'], kind, value)
            if key in seen:
                parents[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    for group in groups.values():
        tag = str(group[0]['event']) + '-' + str(min(r['id'] for r in group))
        for row in group:
            row['group'] = tag
            row['same_location_records'] = len(group)


def screen(originals, geometry, river, radius_m=600):
    river = ' '.join(river.split()).casefold()
    if not river or len(river) > 160 or not 0 < radius_m <= 5000:
        raise ValueError('Check river name and search distance / 请核对河名及搜索距离')
    crs = CRS.from_user_input(geometry['crs'])
    scale = crs.axis_info[0].unit_conversion_factor
    transform = Transformer.from_crs(4326, crs, always_xy=True)
    paths = [segments(x) for x in geometry['paths']]
    cuts = [(c['rs'], segments(c['xy'])) for c in geometry['cuts']]
    exclusions = Counter()
    rows = []
    checked = set()
    for event, raw in originals:
        data = json.loads(raw)
        if not isinstance(data, list) or any(not isinstance(r, dict) or r.get('event_id') != event for r in data):
            raise ValueError('USGS returned a different event / USGS 返回事件不一致')
        for index, r in enumerate(data, 1):
            if ' '.join((r.get('waterbody') or '').split()).casefold() != river:
                exclusions['waterbody'] += 1
                continue
            lon, lat = r.get('longitude_dd'), r.get('latitude_dd')
            if not all(type(v) in (float, int) and math.isfinite(v) for v in (lon, lat)) or abs(lon)>180 or abs(lat)>90:
                exclusions['coordinates'] += 1
                continue
            xy = np.asarray(transform.transform(lon, lat, errcheck=True))
            lateral = min(distance(xy, s) for s in paths) * scale
            if lateral > radius_m:
                exclusions['distance'] += 1
                continue
            signature = (event, r.get('id'))
            if type(signature[1]) != int or signature in checked:
                raise ValueError('Invalid or duplicated USGS mark ID / USGS 洪痕编号缺失或重复')
            checked.add(signature)
            d, rs = min((distance(xy, s) * scale, rs) for rs, s in cuts)
            z = r.get('elev_ft')
            rows.append(dict(id=r['id'], event=event, line=index, site=r.get('site_number'), xy=xy.tolist(),
                             lonlat=[lon, lat], site_lonlat=[r.get('site_longitude'), r.get('site_latitude')],
                             rs=rs, lateral_m=round(lateral,2), cut_distance_m=round(d,2),
                             location=r.get('location_description'), description=r.get('site_description'),
                             notes=r.get('notes'), side=crossing_side(r), bank=r.get('bank'),
                             datum=r.get('vertical_datum_name'), quality=r.get('hwm_quality_name'),
                             survey=r.get('vertical_method_name'), z_ft=z,
                             datum_matches=bool(datum(geometry.get('datum'))) and datum(r.get('vertical_datum_name')) == datum(geometry['datum'])))
    rows.sort(key=lambda r:(r['event'],r['id']))
    grouped(rows)
    end_rs = min(cuts,key=lambda c:float(c[0]))[0]
    outlet_groups = {r['group'] for r in rows if r['rs']==end_rs}
    for row in rows:
        gage = re.search(r'\b(?:streamgage|gage|gauge)\s*(\d{8,15})\b',row['description'] or '',re.I)
        row['referenced_gage'] = gage[1] if gage else None
        if row['group'] in outlet_groups:
            row['suggestion'] = 'review_outlet_crossing'
        elif row['referenced_gage']:
            row['suggestion'] = 'review_gage_crossing'
        elif not row['datum_matches']:
            row['suggestion'] = 'review_vertical_reference'
        else:
            row['suggestion'] = 'review_independent_location'
    return dict(rows=rows, excluded=dict(exclusions), cuts=geometry['cuts'], location_groups=len({r['group'] for r in rows}))
