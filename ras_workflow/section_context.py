"""Link section hydraulics, tested boundary changes and spatial evidence to one sealed run."""
import base64
import io

import h5py
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds

from .common import ROOT, digest, intact, lock, read, safe_path, save, unique_id
from .public_reach import ROADS, query
from .qa import BASE, number, verified_profiles
from .result_atlas import assemble, native_rows
from .revision_inputs import bound_inputs, station_key
from .source_fetch import Download

NLD='https://geospatial.sec.usace.army.mil/dls/rest/services/NLD/Public/FeatureServer/7'


def frame(summary):
    _,geometry,sources=bound_inputs(summary)
    hyd=summary['hydraulics']
    verified_profiles(hyd)
    rows=assemble(native_rows(hyd),None,geometry)['sections']
    profiles=[p['profile_id'] for p in hyd['profiles']]
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as h:
        block=h[BASE+'/Cross Sections']
        flows=block['Flow'][:]
        extra=block.get('Additional Variables')
        arrays=[extra[k][:] if extra is not None and k in extra else None for k in ('Flow Left OB','Flow Right OB')]
        if flows.shape!=(len(profiles),len(geometry['cross_sections'])):raise ValueError('Section count differs from native flow table')
        for row,indices in zip(rows,np.ndindex(flows.shape),strict=True):
            q=number(flows[indices]);row['rs']=station_key(row['rs'])
            row['flow_cfs']=q
            shares=[]
            for a in arrays:
                v=number(a[indices]) if a is not None else None
                shares.append(100*v/q if v is not None and abs(v)<1e20 and q and q>0 else None)
            row['ob_percent']=shares
    return rows,geometry['horizontal_crs'],sources+[hyd['raw_hdf'],hyd['raw_controller']]


def extent(frames):
    lines=[r['map']['cutline_xy'] for rows in frames.values() for r in rows if r['map']]
    if not lines:raise ValueError('No sealed cross section locations')
    xy=np.concatenate(lines)
    low=xy.min(axis=0);high=xy.max(axis=0);pad=max(float(max(high-low))*.04,1)
    return [*(low-pad).tolist(),*(high+pad).tolist()]


def backdrop(model,bounds,crs):
    delivery=model.get('latest_delivery') or {}
    if delivery.get('summary')!=model['summary']:return dict(status='NO_MATCHING_DELIVERY')
    pack=delivery.get('complete',{});entry=pack.get('manifest')
    if not entry or not intact([entry]):return dict(status='MANIFEST_UNAVAILABLE')
    found=next((r for r in read(ROOT/entry['path'])['files'] if r['path']=='GIS/Aerial.tif'),None)
    if not found:return dict(status='IMAGERY_UNAVAILABLE')
    src=safe_path(safe_path(ROOT,pack['path']),found['path'])
    verified=dict(found,path=src.relative_to(ROOT).as_posix())
    if not intact([verified]):return dict(status='IMAGERY_CHANGED')
    span=np.array(bounds[2:])-bounds[:2]
    width,height=np.maximum(1,np.rint(span*1250/max(span)).astype(int))
    transform=from_bounds(*bounds,width,height)
    with rasterio.open(src) as source:
        if not source.crs or source.count<3:return dict(status='RGB_OR_CRS_UNAVAILABLE')
        with WarpedVRT(source,crs=crs,transform=transform,width=int(width),height=int(height),resampling=Resampling.bilinear) as vrt:
            data=vrt.read([1,2,3],out_dtype='uint8',masked=True).filled(235)
    buf=io.BytesIO();Image.fromarray(np.moveaxis(data,0,-1)).save(buf,'JPEG',quality=84)
    return dict(status='READY',source=verified,bounds=bounds,uri='data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode('ascii'))


def public_lines(directory,bounds,crs,fetch):
    bbox=transform_bounds(crs,'EPSG:4326',*bounds,densify_pts=21)
    if not np.isfinite(bbox).all() or max(bbox[2]-bbox[0],bbox[3]-bbox[1])>0.35:
        return [dict(kind='coverage',status='EXTENT_UNSUPPORTED',lines=[])]
    transform=Transformer.from_crs(4326,crs,always_xy=True)
    base=directory/'context_layers'/digest([crs,bounds])[:20]
    download=None
    layers=[('roads_'+str(i),ROADS+str(i),"MTFCC IN ('S1100','S1200','S1400')",'NAME,MTFCC') for i in (2,6,8)]
    layers.append(('levees',NLD,'1=1','SYSTEM_NAME,ALIGN_TYPE'))
    result=[]
    for kind,url,where,fields in layers:
        receipt=base/(kind+'.json')
        cached=read(receipt) if receipt.exists() else {}
        try:
            if not cached.get('source') or not intact([cached['source']]):
                if not fetch:
                    result.append(dict(kind=kind,status='NOT_LOADED',lines=[]));continue
                base.mkdir(parents=True,exist_ok=True)
                if download is None:
                    download=Download(limit=20_000_000,timeout=10)
                _,src=query(download,url,bbox,where,fields,base/(kind+'_'+unique_id()+'.json'))
                cached=dict(source=src);save(receipt,cached)
            features=read(ROOT/cached['source']['path'])['features']
            lines=[]
            for f in features:
                attrs=f.get('attributes',{})
                for vertices in (f.get('geometry') or {}).get('paths',[]):
                    xy=np.asarray(vertices,float)
                    if len(xy)<2:continue
                    pts=np.column_stack(transform.transform(xy[:,0],xy[:,1]))
                    if np.isfinite(pts).all():lines.append(dict(name=attrs.get('NAME') or attrs.get('SYSTEM_NAME') or '',xy=pts.round(3).tolist()))
            result.append(dict(kind=kind,status='AVAILABLE' if lines else 'NO_FEATURES_RETURNED',lines=lines,source=cached['source']))
        except (OSError,ValueError,KeyError) as error:
            result.append(dict(kind=kind,status='UNAVAILABLE',error=str(error),lines=[]))
    return result


def boundary_series(studies):
    series=[]
    for study in studies:
        cases={c['id']:c.get('changes',[]) for c in study['cases']}
        for cmp in study['comparisons']:
            changes=cases[cmp['case']]
            if len(changes)!=1:continue
            ch=changes[0]
            if not ch['path'].startswith(('boundary_slopes.','boundaries.')):continue
            for profile in sorted({r['profile'] for r in cmp['cross_section_differences']}):
                points={station_key(r['station']):r['delta_wse_ft'] for r in cmp['cross_section_differences'] if r['profile']==profile}
                series.append(dict(case=cmp['case'],profile=profile,change=ch,by_rs=points,source=study['analysis']))
    return series


def collect(key,body):
    from .app_core import folder
    from .result_guidance import load_evidence
    from .report_studies import collect as studies
    from .river_review_report import collect as reviews
    model,path,summary,_,_,errors=load_evidence(key,body)
    if model.get('model_type')!='river':raise ValueError('Choose a solved river reach')
    rows,crs,sources=frame(summary);frames={'baseline':rows}
    entry=model.get('latest_geometry_comparison')
    if entry:
        try:
            audited,refs=reviews(path,summary)
            if 'comparison' in audited:
                result=read(ROOT/entry['path'])
                for name in ('fixed','rotated'):
                    variant,other_crs,bound=frame(read(ROOT/result['summaries'][name]['path']))
                    if crs!=other_crs:raise ValueError('Revisions have different coordinate systems')
                    frames[name]=variant;sources.extend(bound)
                sources.extend(refs)
        except (OSError,ValueError,KeyError) as error:
            frames={'baseline':rows};errors.append('Geometry comparison: '+str(error))
    try:
        runs,refs=studies(path,summary);series=boundary_series(runs);sources.extend(refs)
    except (OSError,ValueError,KeyError) as error:
        series=[];errors.append('Boundary comparisons: '+str(error))
    bounds=extent(frames)
    try:aerial=backdrop(model,bounds,crs)
    except (OSError,ValueError,KeyError) as error:
        aerial=dict(status='UNAVAILABLE',error=str(error))
    directory=folder(key)
    if body.get('load_layers') is True:
        with lock(directory/'context_layers'/'fetch.lock'):layers=public_lines(directory,bounds,crs,True)
    else:layers=public_lines(directory,bounds,crs,False)
    return dict(frames=frames,boundaries=series,bounds=bounds,crs=crs,imagery=aerial,layers=layers,errors=errors,
                baseline=model['summary'],sources=list({e['path']:e for e in sources}.values()))
