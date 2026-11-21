"""USGS TNM discovery/download, real raster QA and projected AOI mosaics.

Coordinate-only terrain is exploratory until vertical metadata and alignment
are reviewed. Downloads never become culvert dimensions or flood estimates.
"""
from contextlib import ExitStack
from time import monotonic
import urllib.request, urllib.parse, ssl, json, math, os
import numpy as np
import rasterio
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.transform import from_origin
from pyproj import CRS, Transformer, Geod
from .common import *

def fetch(url,path,budget,progress=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);receipt=path.with_name(path.name+'.request.json')
    if receipt.exists() and path.exists():
        old=read(receipt)
        if old.get('url')==url and old.get('sha256')==sha(path):return old
        raise ValueError('Downloaded cache changed; preserve evidence and choose a new destination: '+rel(path))
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https':raise ValueError('HTTPS data sources only')
    allowed=('usgs.gov','nationalmap.gov','sciencebase.gov','prd-tnm.s3.amazonaws.com','hec.usace.army.mil')
    if not any(parsed.hostname==d or parsed.hostname.endswith('.'+d) for d in allowed):raise ValueError('Public source outside supported allowlist: '+str(parsed.hostname))
    ctx=ssl.create_default_context()
    req=urllib.request.Request(url,headers={'User-Agent':'SteadyReach/0.1'})
    part=path.with_name(path.name+'.partial');total=0
    with urllib.request.urlopen(req,timeout=45,context=ctx) as response:
        declared=int(response.headers.get('Content-Length','0'))
        if declared>budget:raise ValueError(f'File exceeds remaining download budget: {Path(parsed.path).name} requires {declared:,} bytes; {budget:,} bytes remain')
        with part.open('wb') as f:
            last_update=monotonic()
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>budget:raise ValueError('Stream exceeded download budget')
                f.write(chunk)
                if progress and monotonic()-last_update>=5:
                    progress(total,declared)
                    last_update=monotonic()
        if declared and total!=declared:raise ValueError('Incomplete Content-Length')
        record=dict(url=url,resolved_url=response.url,time_utc=utc(),size_bytes=total,sha256=sha(part),
                    content_type=response.headers.get('Content-Type'),tls_verification=True)
    os.replace(part,path);save(receipt,record);return record

def bbox_for(lat,lon,radius):
    if not finite(radius) or not 50<=radius<=5000:raise ValueError('Acquisition buffer must be 50..5000 m')
    geod=Geod(ellps='WGS84')
    pts=[geod.fwd(lon,lat,az,radius*math.sqrt(2))[:2] for az in [45,135,225,315]]
    return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]

def _catalog_covers_bbox(product,bbox):
    """A download-order hint only; raster pixels must still prove coverage."""
    bounds=product.get('boundingBox')
    if not isinstance(bounds,dict):return False
    values=[bounds.get(key) for key in ('minX','minY','maxX','maxY')]
    if not all(finite(value) for value in values):return False
    return values[0]<=bbox[0] and values[1]<=bbox[1] and values[2]>=bbox[2] and values[3]>=bbox[3]

def candidates(path,c,folder):
    location=c.get('location')
    if not location:raise ValueError('WGS84 coordinate required for DEM query')
    lat,lon=location['latitude'],location['longitude']
    # This broad extent is only a service guard; actual coverage is checked below.
    if not (-180<=lon<=-60 and 17<=lat<=73):raise ValueError('USGS workflow currently restricted to US coverage; configure a local DEM elsewhere')
    t=c['terrain'];bbox=bbox_for(lat,lon,t['buffer_m'])
    folder.mkdir(parents=True,exist_ok=True)
    endpoint='https://tnmaccess.nationalmap.gov/api/v1/'
    fetch(endpoint+'datasets',folder/'datasets.json',10_000_000)
    datasets=read(folder/'datasets.json')
    def walk(xs):
        if isinstance(xs,dict):
            yield xs
            for v in xs.values():
                if isinstance(v,(list,dict)):yield from walk(v)
        elif isinstance(xs,list):
            for x in xs:yield from walk(x)
    labels=sorted(set(x.get('sbDatasetTag','') for x in walk(datasets) if t['dataset_contains'].lower() in x.get('sbDatasetTag','').lower() and 'DEM' in x.get('sbDatasetTag','')))
    if len(labels)!=1:raise ValueError('Dataset selection is ambiguous/unavailable: '+str(labels))
    products=[];offset=0
    while True:
        query=dict(bbox=','.join(str(v) for v in bbox),datasets=labels[0],max=100,offset=offset)
        url=endpoint+'products?'+urllib.parse.urlencode(query);dest=folder/f'products_{offset}.json';fetch(url,dest,20_000_000)
        data=read(dest);batch=data.get('items',[]);products.extend(batch);offset+=len(batch)
        if offset>=data.get('total',len(products)):break
        if not batch or offset>1000:raise ValueError('Unbounded/inconsistent catalog paging')
    if not products:raise ValueError('No products intersect acquisition AOI')
    if t.get('required_survey'):
        products=[p for p in products if survey_key(p['downloadURL'])==t['required_survey']]
        if not products:raise ValueError('No adjoining products from the working DEM survey')
    selected=t.get('selected_source_ids')
    if selected:
        products=[p for p in products if p['sourceId'] in selected]
        if set(selected)!={p['sourceId'] for p in products}:raise ValueError('Requested products absent from current catalog')
    # Do not mix overlapping projects/epochs without an explicit selection.
    # Prefer a candidate covering the AOI among equally recent products. TNM
    # returns overlapping UTM-zone tiles; downloading partial tiles first can
    # exhaust the budget before reaching an equally recent complete tile.
    # Keep publication priority and the actual cell/NoData check in acquire().
    products=sorted(products,key=lambda p:(p.get('publicationDate') or '',_catalog_covers_bbox(p,bbox)),reverse=True)
    result=dict(dataset=labels[0],bbox=bbox,products=products,selection='explicit source IDs' if selected else 'newest publication first; within each publication date prefer catalog bounds covering the AOI; actual raster pixels must confirm full coverage; record all contributing products')
    save(folder/'catalog.json',result);return result

def local_info(path,c,folder):
    t=c['terrain'];raster=safe_path(path.parent,t['raster'])
    with rasterio.open(raster) as d:
        if not d.crs:raise ValueError('DEM CRS missing')
        loc=c.get('location')
        if not loc:raise ValueError('Supply the project latitude/longitude to check local DEM coverage / 请补充项目经纬度以检查本地 DEM 覆盖范围')
        x,y=Transformer.from_crs(4326,d.crs,always_xy=True).transform(loc['longitude'],loc['latitude'])
        sample=next(d.sample([(x,y)],masked=True))
        if np.ma.getmaskarray(sample).any() or not np.isfinite(sample.data).all():raise ValueError('Site lies outside valid DEM')
        result=dict(status='READY_WITH_LIMITATIONS',mode='local',raster=item(raster,'external_terrain'),
            crs_wkt=d.crs.to_wkt(),resolution=list(d.res),bounds=list(d.bounds),
            vertical_unit=t.get('vertical_unit'),vertical_datum=t.get('vertical_datum'),
            metadata=item(safe_path(path.parent,t['provenance'])) if t.get('provenance') else None,
            limitations=['External surface only; cannot identify buried culvert inverts','Input metadata inherited explicitly from project configuration'])
    save(folder/'terrain.json',result);return result

def survey_key(url):
    parts=Path(urllib.parse.urlsplit(url).path).parts
    return parts[parts.index('Projects')+1] if 'Projects' in parts and parts.index('Projects')+1<len(parts) else None


def mosaic(files,bbox):
    crs=CRS.from_wkt(files[0]['source_crs']).to_2d()
    if not crs.is_projected:raise ValueError('USGS source needs a projected CRS')
    bounds=transform_bounds(4326,crs,*bbox,densify_pts=21)
    resolution=1./crs.axis_info[0].unit_conversion_factor
    width=math.ceil((bounds[2]-bounds[0])/resolution);height=math.ceil((bounds[3]-bounds[1])/resolution)
    transform=from_origin(bounds[0],bounds[3],resolution,resolution)
    dest=np.full((height,width),np.nan,dtype='float32');overlap=0
    for source in files:
        with rasterio.open(ROOT/source['source']['path']) as src:
            native=CRS.from_user_input(src.crs).to_2d()
            if not native.is_projected or max(src.res)*native.axis_info[0].unit_conversion_factor>1.05:
                raise ValueError('1m dataset disagrees with actual resolution; review required')
            if native.datum!=crs.datum:raise ValueError('DEM horizontal datums differ; review product selection')
            temp=np.full_like(dest,np.nan)
            reproject(rasterio.band(src,1),temp,src_transform=src.transform,src_crs=native.to_wkt(),src_nodata=src.nodata,
                dst_transform=transform,dst_crs=crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
            valid=np.isfinite(temp);missing=~np.isfinite(dest)
            overlap+=int((valid & ~missing).sum())
            dest[missing & valid]=temp[missing & valid]
    return dest,crs,transform,overlap


def acquire(path,c,folder,progress=None):
    t=c.get('terrain',{})
    if t.get('mode')=='not_applicable':
        result=dict(status='NOT_APPLICABLE',reason=t.get('reason') or ('Official 1D benchmark has native station-elevation sections; no georeferenced terrain is asserted' if c.get('case_kind')=='official_benchmark' else 'Terrain acquisition is explicitly disabled in this configuration; no geographic coverage is asserted'))
        save(folder/'terrain.json',result);return result
    if t.get('mode')=='local':return local_info(path,c,folder)
    if t.get('mode')!='usgs':raise ValueError('Unknown terrain mode')
    if progress:progress('Querying USGS DEM catalog / 正在查询 USGS 地形目录')
    catalog=candidates(path,c,folder/'catalog');budget=t['max_download_bytes'];remaining=budget;network_bytes=0
    groups={};best_fraction=-1.;best=None
    for p in catalog['products']:
        url=p['downloadURL'];suffix=Path(urllib.parse.urlparse(url).path).suffix.lower()
        if suffix not in ['.tif','.tiff']:raise ValueError('Only actual GeoTIFF products supported; no archive guessed')
        cache=ROOT/'data/workflow_cache'/hashlib.sha256(url.encode()).hexdigest()[:20]/Path(urllib.parse.urlparse(url).path).name
        cached=cache.is_file() and cache.with_name(cache.name+'.request.json').is_file()
        label=('Checking cached DEM / 正在核验缓存地形' if cached else 'Downloading DEM / 正在下载地形')+' · '+cache.name
        def report_bytes(received,declared):
            size=f'{received/1048576:.1f}' + (f' / {declared/1048576:.1f}' if declared else '')+' MiB'
            progress(label+' · '+size)
        if progress:
            progress(label)
            receipt=fetch(url,cache,remaining,progress=report_bytes)
            progress('Checking elevation coverage / 正在检查高程覆盖 · '+cache.name)
        else:
            receipt=fetch(url,cache,remaining)
        remaining-=receipt['size_bytes']
        if not cached:network_bytes+=receipt['size_bytes']
        if remaining<0:raise ValueError('Aggregate selection exceeds configured download budget')
        metadata=None
        if p.get('metaUrl'):
            meta=cache.parent/'metadata_page.html'
            try:fetch(p['metaUrl'],meta,min(remaining,10_000_000));metadata=item(meta,'product_metadata')
            except Exception as e:metadata=dict(status='FAILED',error=str(e),url=p['metaUrl'])
        with rasterio.open(cache) as src:
            if not src.crs or src.count!=1:raise ValueError('Unsupported/missing GeoTIFF CRS or bands')
            product=dict(product_id=p['sourceId'],title=p['title'],url=url,source=item(cache,'USGS_original_DEM'),metadata=metadata,
                source_crs=src.crs.to_wkt(),resolution=list(src.res),bounds=list(src.bounds),nodata=src.nodata,
                publication_date=p.get('publicationDate'),last_updated=p.get('lastUpdated'),
                catalog_description=p.get('body'),vertical_datum='unreviewed',vertical_unit='unreviewed')
        group='user_selection' if t.get('selected_source_ids') else survey_key(url) or url
        group_files=groups.setdefault(group,[]);group_files.append(product)
        # Prefer one complete tile; otherwise only combine adjoining products
        # from the same named survey until the actual working grid is complete.
        options=[[product],list(group_files)] if len(group_files)>1 else [[product]]
        for files in options:
            grid=mosaic(files,catalog['bbox'])
            fraction=float(np.isfinite(grid[0]).mean())
            if fraction>best_fraction:
                best_fraction=fraction;best=(files,grid)
            if fraction==1.:break
        if best_fraction==1.:break
    if best is None:raise ValueError('No compatible USGS raster products')
    files,(dest,crs,transform,overlap)=best;height,width=dest.shape
    valid=np.isfinite(dest)
    if not valid.any():raise ValueError('Downloaded raster has no valid AOI cells')
    out=folder/'terrain_aoi.tif'
    with rasterio.open(out,'w',driver='GTiff',height=height,width=width,count=1,dtype='float32',crs=crs,transform=transform,nodata=np.nan,compress='deflate') as d:
        d.write(dest,1);d.update_tags(VERTICAL_DATUM='UNREVIEWED',VERTICAL_UNIT='UNREVIEWED',PROVENANCE='USGS standard 1m; bilinear horizontal projection/crop; no vertical transformation')
    result=dict(status='READY_EXPLORATORY' if valid.all() else 'PARTIAL_COVERAGE',mode='usgs',bbox=catalog['bbox'],
        raster=item(out,'working_DEM'),products=files,download_bytes=budget-remaining,new_dem_download_bytes=network_bytes,valid_fraction=float(valid.mean()),
        nodata_pixels=int((~valid).sum()),overlapping_valid_cells=overlap,crs_wkt=crs.to_wkt(),resolution_m=1,
        horizontal_datum_policy='Retain original product datum; no automatic datum conversion',
        vertical_unit='UNREVIEWED',vertical_datum='UNREVIEWED',
        limitations=['Product XML vertical units/datum/acquisition dates require review before hydraulic sampling',
            'Acquisition coverage does not verify crossing position or flow direction','No culvert geometry inferred from DEM',
            'No field calibration','Overlapping products use catalog order and must be reviewed when overlap is nonzero'])
    save(folder/'terrain.json',result);plot(out,folder/'terrain_map.png',c,result)
    return result

def plot(raster,output,c,info):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with rasterio.open(raster) as d:
        z=d.read(1,masked=True);b=d.bounds
        xy=Transformer.from_crs(4326,d.crs,always_xy=True).transform(c['location']['longitude'],c['location']['latitude'])
        fig,ax=plt.subplots(figsize=(7,6));im=ax.imshow(z,extent=[b.left,b.right,b.bottom,b.top],cmap='terrain')
        ax.plot(*xy,'r+',ms=12,label='Input coordinate (unconfirmed crossing)');ax.legend(fontsize=7)
        unit=CRS.from_user_input(d.crs).axis_info[0].unit_name
        ax.set(title=c['project_id']+' / USGS external terrain',xlabel='Easting ('+unit+')',ylabel='Northing ('+unit+')');ax.ticklabel_format(style='plain',useOffset=False)
        fig.colorbar(im,ax=ax,label='Raw elevation; vertical metadata pending review');fig.tight_layout();fig.savefig(output,dpi=140);plt.close(fig)
