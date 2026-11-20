"""Propose an upstream-to-downstream river reach from public flowlines and roads."""
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

import numpy as np
from pyproj import Transformer

from .common import item, read, save
from .terrain import bbox_for

HYDRO = 'https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6'
ROADS = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/'


def query(download, service, bbox, where, fields, path):
    envelope=','.join(f'{(math.floor(x*10000) if i<2 else math.ceil(x*10000))/10000:.4f}' for i,x in enumerate(bbox))
    url = service + '/query?' + urlencode(dict(f='json', geometry=envelope,
        geometryType='esriGeometryEnvelope', inSR=4326, outSR=4326, spatialRel='esriSpatialRelIntersects',
        returnGeometry='true', where=where, outFields=fields))
    for attempt in range(3):
        try:
            data = download.get(url, limit=9_000_000)
            break
        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt==2 or (isinstance(error,HTTPError) and error.code not in (429,500,502,503,504)):
                raise
            time.sleep(.5*(attempt+1))
    path.write_bytes(data)
    record = dict(**item(path, 'public_map_query'), url=url)
    result = read(path)
    if result.get('error') or result.get('exceededTransferLimit') or 'features' not in result:
        raise ValueError('Incomplete public layer response: ' + service)
    if result.get('features') and result.get('spatialReference', {}).get('wkid') != 4326:
        raise ValueError('Public layer did not return WGS84 coordinates')
    return result['features'], record


def paths(features, transform):
    for feature in features:
        for vertices in feature['geometry']['paths']:
            if len(vertices) < 2:
                continue
            points = np.asarray(vertices, float)[:, :2]
            xy = np.column_stack(transform.transform(*points.T))
            indices = np.r_[True, np.linalg.norm(np.diff(xy, axis=0), axis=1) > .01]
            if indices.sum() > 1:
                yield feature['attributes'], xy[indices]


def project(point, xy):
    edges = np.diff(xy, axis=0)
    lengths = np.linalg.norm(edges, axis=1)
    fraction = np.clip(((point-xy[:-1])*edges).sum(axis=1) / lengths**2, 0, 1)
    distance = np.linalg.norm(xy[:-1]+fraction[:, None]*edges-point, axis=1)
    i = int(np.argmin(distance))
    return float(distance[i]), float(lengths[:i].sum() + fraction[i]*lengths[i])


def joined_channel(segments, pin):
    if not segments:
        raise ValueError('No named downstream-directed USGS channel in the search area')
    ranking = sorted((project(pin, xy)[0], i) for i, (_, xy) in enumerate(segments))
    nearest, index = ranking[0]
    attr, xy = segments[index]
    name = attr['gnis_name']
    if nearest > 150 or any(dist < nearest+25 and segments[i][0]['gnis_name'] != name for dist,i in ranking):
        raise ValueError('The location does not uniquely identify a nearby named channel')
    ids = [attr['permanent_identifier']]
    used = {index}
    for upstream in (True, False):
        while True:
            adjacent = [i for _,i in ranking if i not in used and segments[i][0]['gnis_name'] == name
                        and np.linalg.norm(segments[i][1][-1 if upstream else 0]-xy[0 if upstream else -1]) <= 2]
            if len(adjacent) != 1:
                break
            i = adjacent[0]
            used.add(i)
            part = segments[i][1]
            xy = np.vstack((part[:-1], xy)) if upstream else np.vstack((xy, part[1:]))
            ids.append(segments[i][0]['permanent_identifier'])
    return name, xy, ids


def road_crossings(xy, roads):
    """Intersect segments in metres, recording each distinct along-river crossing."""
    a, edge = xy[:-1], np.diff(xy, axis=0)
    lengths = np.linalg.norm(edge, axis=1)
    chain = np.r_[0., np.cumsum(lengths)]
    left, right = np.minimum(xy[:-1],xy[1:]), np.maximum(xy[:-1],xy[1:])
    def cross(v, w):
        return v[..., 0]*w[..., 1] - v[..., 1]*w[..., 0]
    hits = []
    for attr, road in roads:
        name = attr.get('NAME')
        if not name:
            continue
        for p,q in zip(road, road[1:]):
            indices = np.flatnonzero(((left <= np.maximum(p,q)) & (right >= np.minimum(p,q))).all(axis=1))
            if not len(indices):
                continue
            v, w = edge[indices], q-p
            denom = cross(v,w)
            valid = np.abs(denom) > 1e-7
            t = np.divide(cross(p-a[indices],w),denom,out=np.full_like(denom,np.nan),where=valid)
            u = np.divide(cross(p-a[indices],v),denom,out=np.full_like(denom,np.nan),where=valid)
            for j in np.flatnonzero((0 <= t) & (t <= 1) & (0 <= u) & (u <= 1)):
                i = indices[j]
                hits.append((float(chain[i]+t[j]*lengths[i]),name))
    return sorted(set(hits))


def propose(latitude, longitude, hydro, roads, inset_m=40.):
    zone = min(60, int((longitude+180)//6)+1)
    local = 32600+zone
    forward = Transformer.from_crs(4326, local, always_xy=True)
    backward = Transformer.from_crs(local, 4326, always_xy=True)
    pin = np.asarray(forward.transform(longitude, latitude))
    segments = [(a,p) for a,p in paths(hydro,forward) if a.get('gnis_name') and a.get('flowdir') == 1]
    name, xy, ids = joined_channel(segments, pin)
    _, position = project(pin,xy)
    # Inspect unnamed branches too. A mapped junction gives a review location,
    # not a measured lateral discharge or proof of floodplain connectivity.
    junctions = []
    for attr, line in paths(hydro, forward):
        if attr.get('permanent_identifier') in ids or attr.get('flowdir') != 1:
            continue
        for end, role in ((line[0], 'leaving'), (line[-1], 'entering')):
            distance, station = project(end, xy)
            if distance <= 2:
                junctions.append((station, dict(direction=role, name=attr.get('gnis_name'),
                    source_id=attr.get('permanent_identifier'), lonlat=list(backward.transform(*end)))))

    def candidate(us, ds, setbacks):
        result = reach_between(name,xy,ids,pin,backward,us,ds,setbacks)
        result['mapped_junctions'] = [row for at,row in junctions if us[0]+setbacks[0] < at < ds[0]-setbacks[1]]
        return result
    crossings = road_crossings(xy, paths(roads,forward))
    if len(crossings)<2:
        raise ValueError('Two named road crossings were not found; choose the intended endpoints on the map')
    nearest=min(range(len(crossings)),key=lambda i:abs(crossings[i][0]-position))
    if abs(crossings[nearest][0]-position)<10:
        options=[]
        for i in (nearest-1,nearest):
            if 0<=i<len(crossings)-1:
                try:
                    options.append(candidate(crossings[i],crossings[i+1],[inset_m,inset_m]))
                except ValueError:
                    continue
        if not options:
            raise ValueError('No suitable adjoining reach found at this crossing; select the intended limits on the map')
        return dict(status='CHOOSE_REACH',river=name,options=options,buffer_m=max(r['buffer_m'] for r in options),
                    reason='The project point projects onto a crossing. Choose the intended reach by its road names.')
    up = [hit for hit in crossings if hit[0] < position]
    down = [hit for hit in crossings if hit[0] > position]
    if not up or not down:
        raise ValueError('Two named road crossings do not bracket the location. Select the intended endpoints on the map.')
    us, ds = up[-1], down[0]
    setbacks = [min(inset_m,(position-us[0])/2),min(inset_m,(ds[0]-position)/2)]
    if min(setbacks)<5:
        raise ValueError('The point is on a road crossing. Select the intended side or pick both reach endpoints.')
    return candidate(us,ds,setbacks)


def reach_between(name,xy,ids,pin,backward,us,ds,setbacks):
    start, stop = us[0]+setbacks[0], ds[0]-setbacks[1]
    if stop-start < 75 or stop-start > 3000:
        raise ValueError('Review reach limits: distance between crossing setbacks is outside screening bounds')
    chain = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    # Keep mapped bends within 5 m of each anchor chord, and on long
    # straight reaches keep controls at least every 110 m.
    along = np.unique(np.r_[start,chain[(chain>start)&(chain<stop)],stop])
    route = np.column_stack([np.interp(along,chain,v) for v in xy.T])
    keep = {0,len(route)-1}
    todo = [(0,len(route)-1)]
    while todo:
        i,j = todo.pop()
        if j<=i+1:
            continue
        delta=route[j]-route[i]
        frac=np.clip((route[i+1:j]-route[i])@delta/max(delta@delta,1.e-12),0,1)
        errors=np.linalg.norm(route[i+1:j]-(route[i]+frac[:,None]*delta),axis=1)
        if max(errors) > 5:
            k=i+1+int(np.argmax(errors))
        elif along[j]-along[i] > 110:
            k=i+1+int(np.argmin(abs(along[i+1:j]-(along[i]+along[j])/2)))
        else:
            continue
        keep.add(k);todo.extend([(i,k),(k,j)])
    distances=np.unique(np.r_[along[sorted(keep)],np.linspace(start,stop,1+math.ceil((stop-start)/110))])
    # Avoid nearly coincident controls from the two spacing rules.
    retained=[float(distances[0])]
    for at in distances[1:-1]:
        if at-retained[-1] >= 5 and stop-at >= 5:
            retained.append(float(at))
    retained.append(stop)
    anchors=np.column_stack([np.interp(retained,chain,v) for v in xy.T])
    radius=max(300,50*math.ceil((np.max(abs(route-pin))+220)/50))
    if radius > 1950:
        raise ValueError('The mapped reach exceeds the automatic DEM area. Review a shorter reach or import suitable terrain.')
    return dict(status='CANDIDATE',river=name,upstream_crossing=us[1],downstream_crossing=ds[1],
                inset_m=setbacks,length_m=stop-start,buffer_m=radius,segment_ids=ids,
                anchor_lonlat=np.column_stack(backward.transform(*anchors.T)).tolist(),
                basis='USGS downstream-directed NHD flowline and intersecting Census road centerlines. Inward offsets are capped at 40 m and half the distance to the projected pin. Confirm crossing identity and backwater independently.')


def discover(location, directory):
    from .source_fetch import Download
    download = Download(limit=36_000_000, timeout=18)
    lat,lon = location['latitude'],location['longitude']
    bbox = bbox_for(lat,lon,1800)
    directory.mkdir(parents=True,exist_ok=True)
    sources=[]
    try:
        try:
            hydro,source=query(download,HYDRO,bbox,'ftype IN (460,558)','OBJECTID,gnis_name,permanent_identifier,flowdir,ftype',directory/'flowlines.json')
            sources.append(source)
        except (OSError,ValueError) as service_error:
            from .hydro_archive import flowlines
            failure=directory/'map_service_attempt.json'
            save(failure,dict(service=HYDRO,reason=str(service_error),bbox=bbox))
            sources.append(item(failure,'map_service_attempt'))
            hydro,archive_sources=flowlines(bbox,directory/'subbasin')
            sources.extend(archive_sources)
        roads=[]
        for layer in (2,6,8):
            features,source=query(download,ROADS+str(layer),bbox,"MTFCC IN ('S1100','S1200','S1400')",'OBJECTID,NAME,MTFCC',directory/f'roads_{layer}.json')
            roads.extend(features);sources.append(source)
        result=propose(lat,lon,hydro,roads)
    except OSError as error:
        result=dict(status='LOOKUP_FAILED',reason=str(error))
    except (ValueError, KeyError) as error:
        result=dict(status='NEEDS_MAP_SELECTION',reason=str(error))
    result['sources']=sources
    save(directory/'candidate.json',result)
    return item(directory/'candidate.json','public_reach_candidate')
