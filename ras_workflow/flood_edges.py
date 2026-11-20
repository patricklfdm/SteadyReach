"""Compare outer wetted limits of native sections with a dated mapped flood edge."""
import io
import json
import math
from pathlib import Path
from statistics import median
from xml.etree import ElementTree
from zipfile import ZipFile

import numpy as np
from pyproj import CRS, Transformer
from .common import finite
from .public_reach import project
from .result_atlas import line_point


def read_lines(name, raw, layer=''):
    ext = Path(name).suffix.lower()
    if len(raw)>10_000_000:
        raise ValueError('Crop the flood-edge file to 10 MB')
    lines = []
    if ext in ('.geojson','.json'):
        data = json.loads(raw.decode('utf-8-sig'))
        if data.get('crs'):
            raise ValueError('Export RFC 7946 GeoJSON in WGS84 longitude/latitude')
        geometries = [f['geometry'] for f in data['features']] if data.get('type')=='FeatureCollection' else [data.get('geometry',data)]
        for geom in geometries:
            kind,coords = geom['type'],geom['coordinates']
            if kind=='LineString':lines.append(coords)
            elif kind in ('MultiLineString','Polygon'):lines.extend(coords)
            elif kind=='MultiPolygon':lines.extend(ring for polygon in coords for ring in polygon)
            else:raise ValueError('Select line or polygon flood edges only')
    elif ext in ('.kml','.kmz'):
        if ext=='.kmz':
            with ZipFile(io.BytesIO(raw)) as archive:
                candidates=[i for i in archive.infolist() if i.filename.lower().endswith('.kml')]
                if len(candidates)!=1 or candidates[0].file_size>10_000_000:
                    raise ValueError('Select one KML with up to 10 MB of geometry')
                raw=archive.read(candidates[0])
        if b'<!doctype' in raw.lower():raise ValueError('KML document type declarations are unsupported')
        root=ElementTree.fromstring(raw)
        folders=root.findall('.//{*}Folder')
        if folders:
            names=[f.findtext('{*}name','').strip() for f in folders]
            if not layer and len(folders)==1:root=folders[0]
            elif layer and names.count(layer)==1:root=folders[names.index(layer)]
            else:raise ValueError('Select one exact flood layer: '+', '.join(names)[:900])
            if root.findall('.//{*}Folder'):raise ValueError('Select a single flood sublayer')
        for tag in ('LineString','LinearRing'):
            for node in root.findall('.//{*}'+tag+'/{*}coordinates'):
                lines.append([list(map(float,point.split(',')[:2])) for point in (node.text or '').split()])
    else:raise ValueError('Use a WGS84 GeoJSON, KML or KMZ flood edge')
    if not lines or sum(len(line) for line in lines)>150_000:
        raise ValueError('Select a nonempty flood extent with up to 150,000 vertices')
    output=[]
    for line in lines:
        if len(line)<2 or any(not isinstance(p,(list,tuple)) or len(p)<2 or
                not finite(p[0]) or not finite(p[1]) or abs(p[0])>180 or abs(p[1])>90 for p in line):
            raise ValueError('Invalid WGS84 coordinates on a flood edge')
        output.append(np.asarray([p[:2] for p in line],float))
    return output


def intersections(cut, starts, ends):
    distances=[]
    cumulative=0.
    for a,b in zip(cut,cut[1:]):
        v=b-a
        length=float(np.linalg.norm(v))
        if length==0:continue
        pick=((np.minimum(starts,ends)<=np.maximum(a,b)+1e-8)&
              (np.maximum(starts,ends)>=np.minimum(a,b)-1e-8)).all(axis=1)
        p=starts[pick]
        w=ends[pick]-p
        def cross(first,second):
            return first[...,0]*second[...,1]-first[...,1]*second[...,0]
        denom=cross(v,w)
        parallel=np.abs(denom)<1e-10
        if np.any(parallel & (np.abs(cross(p-a,v))<1e-8*length)):
            return [],True
        t=np.divide(cross(p-a,w),denom,where=~parallel,out=np.full(len(p),np.nan))
        u=np.divide(cross(p-a,v),denom,where=~parallel,out=np.full(len(p),np.nan))
        inside=(t>=-1e-9)&(t<=1+1e-9)&(u>=-1e-9)&(u<=1+1e-9)
        distances.extend((cumulative+np.clip(t[inside],0,1)*length).tolist())
        cumulative+=length
    return sorted(set(round(d,6) for d in distances)),False


def compare(lines, projection, sections, centers, search_m=400.):
    crs=CRS.from_user_input(projection)
    if not crs.is_projected or not finite(search_m) or not 0<=search_m<=2000:
        raise ValueError('Use a projected model and a 0–2,000 m search beyond cut ends')
    scale=crs.axis_info[0].unit_conversion_factor
    transform=Transformer.from_crs(4326,crs,always_xy=True)
    projected=[np.column_stack(transform.transform(*line.T,errcheck=True)) for line in lines]
    starts=np.concatenate([line[:-1] for line in projected])
    ends=np.concatenate([line[1:] for line in projected])
    distinct=(starts!=ends).any(axis=1)
    starts,ends=starts[distinct],ends[distinct]
    all_errors=[];rows=[]
    for section in sections:
        rs=section['rs'];mapping=section.get('map') or {}
        row=dict(rs=rs,wse_ft=section['wse_ft'],status='NO_NATIVE_WET_EDGE')
        rows.append(row)
        if not mapping.get('wet_segments_xy') or rs not in centers:continue
        cut=np.asarray(mapping['cutline_xy'],float)
        cut=cut[np.r_[True,(np.diff(cut,axis=0)!=0).any(axis=1)]]
        if len(cut)<2:continue
        left,right=cut[0]-cut[1],cut[-1]-cut[-2]
        ray=search_m/scale
        full=np.vstack((cut[0]+ray*left/np.linalg.norm(left),cut,cut[-1]+ray*right/np.linalg.norm(right))) if ray else cut
        hits,coincident=intersections(full,starts,ends)
        length=float(np.linalg.norm(np.diff(full,axis=0),axis=1).sum())
        center=project(np.asarray(centers[rs]),full)[1]
        left_hits=[s for s in hits if s<center];right_hits=[s for s in hits if s>center]
        row.update(status='AMBIGUOUS_OR_MISSING_EDGE',left_hits=len(left_hits),right_hits=len(right_hits),cutline_xy=cut.tolist())
        if coincident or len(hits)!=2 or len(left_hits)!=1 or len(right_hits)!=1:continue
        a,b=hits
        wet=mapping['wet_segments_xy']
        pair=[wet[0][0],wet[-1][-1]]
        w0,w1=[project(np.asarray(p),full)[1] for p in pair]
        errs=[(w0-a)*scale,(b-w1)*scale]
        row.update(status='MATCHED',left_shortfall_m=round(errs[0],3),right_shortfall_m=round(errs[1],3),
                   beyond_cut_m=[round(scale*max(0.,ray-a),3),round(scale*max(0.,b-length+ray),3)],
                   observed_xy=[line_point(full,a/length),line_point(full,b/length)],model_xy=pair)
        all_errors.extend(abs(v) for v in errs)
    return dict(rows=rows,matched=len(all_errors)//2,total=len(rows),
                median_abs_m=round(median(all_errors),3) if all_errors else None)
