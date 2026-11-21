"""Locate records near a proposed reach without treating a gage as its tailwater."""
import re
from .usgs_water import pages, query

from pyproj import Geod, Transformer
from pyproj.exceptions import ProjError

from .common import finite, item
from .review_evidence import WATER, gage_manuscript, rating
from .terrain import bbox_for


def lookup(location, out, download):
    lat, lon = location['latitude'], location['longitude']
    box = ','.join(str(v) for v in bbox_for(lat,lon,2000))
    url = query('monitoring-locations', bbox=box, limit=200)
    result = dict(route='USGS_boundary_records',status='UNAVAILABLE',sources=[],stations=[],failures=[])

    def fetch(name, address):
        raw = download.get(address)
        path = out/name
        path.write_bytes(raw)
        result['sources'].append(dict(**item(path),url=address))
        return raw

    try:
        features = []
        for index, (address, raw, page) in enumerate(pages(url, download.get)):
            path = out / ('early_gages.json' if index == 0 else f'early_gages_{index + 1}.json')
            path.write_bytes(raw)
            result['sources'].append(dict(**item(path), url=address))
            features.extend(page['features'])
        geod = Geod(ellps='WGS84')
        for feature in features:
            props = feature['properties']
            identifier = props.get('id') or feature.get('id') or ''
            if not re.fullmatch(r'USGS-\d+', identifier) or props.get('site_type_code') != 'ST':
                continue
            xy = feature['geometry']['coordinates'][:2]
            distance = geod.inv(lon,lat,*xy)[2]
            if distance <= 2000:
                result['stations'].append(dict(station=identifier[5:],name=props.get('monitoring_location_name'),
                    lonlat=xy,distance_to_pin_m=round(distance,1),datum=props.get('vertical_datum')))
        result['stations'].sort(key=lambda row:row['distance_to_pin_m'])

    except (OSError,KeyError,ValueError,TypeError) as error:
        result['failures'].append(str(error))
        return result
    for row in result['stations'][:2]:
        station = row['station']
        for kind,address,reader in (
            ('rating',WATER+'/stac-files/ratings/USGS.'+station+'.exsa.rdb',lambda raw:rating(raw,station,{})),
            ('history','https://sims-manuscripts-bucket.s3.us-west-2.amazonaws.com/sims_USGS_'+station+'.xml',
             lambda raw:gage_manuscript(raw,station))):
            try:
                row[kind] = reader(fetch(f'early_{station}_{kind}.txt',address))
            except (OSError,KeyError,ValueError,TypeError) as error:
                result['failures'].append(f'{station} {kind}: {error}')
    result['status'] = 'PARTIAL' if result['failures'] else 'CANDIDATES' if result['stations'] else 'NO_RECORDS'
    return result


def screen(attempt, geometry, model, reach, profiles):
    from .river_observations import MAX_MATCH_M
    downstream = None
    sections = geometry.get('cross_sections') or []
    if sections and geometry.get('horizontal_crs'):
        valid = [s for s in sections if finite(s.get('rs')) and len(s.get('center_xy') or [])==2]
        if valid:
            last = min(valid,key=lambda s:s['rs'])
            try:
                downstream = Transformer.from_crs(geometry['horizontal_crs'],4326,always_xy=True).transform(*last['center_xy'],errcheck=True)
            except (ProjError, TypeError, ValueError):
                downstream = None
    picks=model.get('map_picks',{}).get('river') or []
    if not downstream and len(picks)>=2:
        crs=(model.get('terrain') or {}).get('crs_wkt')
        if crs:
            try:
                downstream=Transformer.from_crs(crs,4326,always_xy=True).transform(*picks[-1],errcheck=True)
            except (ProjError,TypeError,ValueError):
                downstream=None
    if not downstream and reach.get('anchor_lonlat') and not picks:
        downstream = reach['anchor_lonlat'][-1]
    result = []
    for row in attempt.get('stations',[]):
        distance = Geod(ellps='WGS84').inv(*downstream,*row['lonlat'])[2] if downstream else None
        band = row.get('rating',{})
        result.append(dict(station=row['station'],name=row['name'],pin_m=row['distance_to_pin_m'],
            boundary_m=round(distance,1) if distance is not None else None,
            transfer_required=distance>MAX_MATCH_M if distance is not None else None,
            datum=row.get('datum'),gage_history=row.get('history'),rating_dates=band.get('validity',[]),
            outside_rating=[p['id'] for p in profiles if finite(p.get('flow_cfs')) and band
                            and not band['min_cfs']<=p['flow_cfs']<=band['max_cfs']]))
    return result
