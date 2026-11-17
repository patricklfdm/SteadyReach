"""Traceable, bounded USGS NAIP map imagery. Never a hydraulic input.

Query the live service schema, lock the returned primary imagery, and use the
export's actual extent. No screenshots, guessed years or local datum shifts.
"""
import json
import math
from urllib.parse import urlencode
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
from rasterio.enums import ColorInterp
from PIL import Image
from pyproj import CRS
from .common import item, read, safe_path, save, ROOT, utc
from .terrain import fetch

SERVICE = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'


def acquire(crs, bounds, output, max_download_bytes=40_000_000, max_pixels=1600):
    """Download a small offline natural-color map in the reviewed model CRS.

    A service failure is actionable, never silently replaced with a blank map.
    Returned image years describe catalog sources, not verified site currency.
    """
    crs=CRS.from_user_input(crs)
    if not crs.is_projected or crs.is_compound:raise ValueError('Imagery needs a reviewed 2D projected geometry CRS')
    if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds) or not (bounds[0]<bounds[2] and bounds[1]<bounds[3]):
        raise ValueError('Invalid imagery extent')
    if type(max_pixels)!=int or not 256<=max_pixels<=3000:raise ValueError('Imagery max_pixels must be 256..3000')
    if type(max_download_bytes)!=int or not 1_000_000<=max_download_bytes<=100_000_000:
        raise ValueError('Imagery download budget must be 1..100 MB')
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False)
    remaining=max_download_bytes;receipts=[]
    def get(url,name,limit):
        nonlocal remaining
        record=fetch(url,folder/name,min(remaining,limit));receipts.append(record);remaining-=record['size_bytes']
        return folder/name
    def get_json(route,params,name):
        result=read(get(SERVICE+route+'?'+urlencode(params),name,5_000_000))
        if 'error' in result:raise ValueError('USGS imagery service: '+json.dumps(result['error']))
        return result
    state=dict(schema_version='naip_acquisition_1.0',status='IN_PROGRESS',started_utc=utc(),service=SERVICE,
               requested_bounds=list(bounds),requested_crs=crs.to_wkt())
    try:
        service=get_json('',dict(f='json'),'service.json')
        fields={f['name']:f for f in service.get('fields',[])}
        required={'Category','Year','acquisition_date','Name',service.get('objectIdField')}
        if not required.issubset(fields):raise ValueError('USGS imagery catalog schema changed; review the saved service description')
        category=fields['Category'].get('domain') or {}
        primary=[v['code'] for v in category.get('codedValues',[]) if v['name']=='Primary']
        # Some service descriptions omit the field domain: the query response
        # must then supply it before an export is permitted.
        functions={v['name'] for v in service.get('rasterFunctionInfos',[])}
        if 'NaturalColor' not in functions or 'LockRaster' not in service.get('allowedMosaicMethods','').split(','):
            raise ValueError('USGS natural-color or locked-source export is unavailable')
        authority=crs.to_authority();sr=int(authority[1]) if authority and authority[0]=='EPSG' else json.dumps(dict(wkt=crs.to_wkt(version='WKT1_ESRI')))
        # Query the catalog in geographic coordinates. The USGS service can
        # return gateway errors for projected JSON envelopes although the same
        # geographic extent succeeds. The exported raster still uses model CRS.
        geographic=transform_bounds(crs,'EPSG:4326',*bounds,densify_pts=21)
        catalog=get_json('/query',dict(f='json',geometry=','.join(map(str,geographic)),geometryType='esriGeometryEnvelope',
            inSR=4326,spatialRel='esriSpatialRelIntersects',outFields='*',returnGeometry='false'), 'catalog.json')
        if catalog.get('exceededTransferLimit'):raise ValueError('Imagery catalog truncated; reduce map extent')
        if not primary:
            category=next((f.get('domain') or {} for f in catalog.get('fields',[]) if f['name']=='Category'),{})
            primary=[v['code'] for v in category.get('codedValues',[]) if v['name']=='Primary']
        if len(primary)!=1:raise ValueError('Cannot identify primary imagery category from service schema')
        records=[f['attributes'] for f in catalog.get('features',[]) if f['attributes'].get('Category')==primary[0]]
        oid=service['objectIdField']
        if not records:raise ValueError('No primary NAIP imagery covers the map extent; supply local imagery or record its absence')
        if any(type(r.get(oid))!=int for r in records):raise ValueError('Invalid imagery catalog identifiers')
        records.sort(key=lambda r:(r.get('acquisition_date') or 0,r[oid]),reverse=True)
        ids=[r[oid] for r in records]
        if len(ids)>min(int(service.get('maxMosaicImageCount',20)),100):raise ValueError('Too many imagery sources; reduce map extent')
        limit=min(max_pixels,int(service['maxImageWidth']),int(service['maxImageHeight']))
        dx=bounds[2]-bounds[0];dy=bounds[3]-bounds[1]
        width=max(1,round(limit*dx/max(dx,dy)));height=max(1,round(limit*dy/max(dx,dy)))
        mosaic=dict(mosaicMethod='esriMosaicLockRaster',lockRasterIds=ids,mosaicOperation='MT_FIRST',ascending=True)
        export=get_json('/exportImage',dict(f='json',bbox=','.join(map(str,bounds)),bboxSR=sr,imageSR=sr,
            size=f'{width},{height}',format='png32',pixelType='U8',adjustAspectRatio='false',
            interpolation='RSP_BilinearInterpolation',mosaicRule=json.dumps(mosaic),renderingRule=json.dumps(dict(rasterFunction='NaturalColor'))),'export.json')
        extent=export['extent'];returned_crs=extent['spatialReference']
        returned_crs=CRS.from_user_input(returned_crs.get('wkt') or returned_crs.get('latestWkid') or returned_crs.get('wkid'))
        if not returned_crs.equals(crs,ignore_axis_order=True):raise ValueError('Export returned a different CRS')
        actual=[extent[k] for k in ['xmin','ymin','xmax','ymax']]
        if not all(math.isfinite(v) for v in actual) or any(abs(a-b)>max(dx,dy)*1e-8 for a,b in zip(actual,bounds)):
            raise ValueError('Export extent differs from requested map extent')
        png=get(export['href'],'image.png',remaining)
        with Image.open(png) as im:
            if im.format!='PNG' or im.size!=(width,height) or im.size!=(export['width'],export['height']):
                raise ValueError('Export image format/dimensions differ from receipt')
            if 'A' not in im.getbands():raise ValueError('PNG export lacks coverage alpha; request an auditable export')
            rgba=np.asarray(im.convert('RGBA'));valid=rgba[:,:,3]==255
        if not valid.all():raise ValueError(f'NAIP imagery does not fully cover map extent ({valid.mean():.2%}); reduce extent or supply local imagery')
        raster=folder/'Aerial.tif'
        years=sorted({r['Year'] for r in records if r.get('Year') is not None})
        label='USGS / USDA NAIP; catalog source years '+(', '.join(map(str,years)) or 'unspecified')
        with rasterio.open(raster,'w',driver='GTiff',height=height,width=width,count=3,dtype='uint8',
                           crs=crs.to_wkt(),transform=from_bounds(*actual,width,height),compress='deflate') as dst:
            dst.write(rgba[:,:,:3].transpose(2,0,1));dst.colorinterp=(ColorInterp.red,ColorInterp.green,ColorInterp.blue)
            dst.update_tags(SOURCE=label,SERVICE=SERVICE,ROLE='Display imagery; not survey or elevation evidence')
        state.update(status='READY_FOR_MAP_REVIEW',raster=item(raster),source=label,source_records=records,
            returned_bounds=actual,rendered_resolution=[dx/width,dy/height],horizontal_unit=crs.axis_info[0].unit_name,
            valid_fraction=float(valid.mean()),mosaic_rule=mosaic,attribution=service.get('copyrightText'),
            limitations=['Service-rendered natural-color mosaic, not an original orthophoto tile',
                'Server performs horizontal projection; service positioning accuracy requires map review',
                'Requested pixel spacing is not source accuracy; imagery is not a culvert survey',
                'Source years may differ from terrain and surveyed hydraulic geometry'])
    except Exception as e:
        state.update(status='FAILED',error=str(e));raise
    finally:
        state.update(finished_utc=utc(),download_bytes=max_download_bytes-remaining,requests=receipts)
        save(folder/'acquisition.json',state)
    return state
