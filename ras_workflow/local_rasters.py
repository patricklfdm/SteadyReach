"""Reuse locally archived acquisition receipts with their exact raster bytes."""
import base64
import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from rasterio.io import MemoryFile


def validate(files,unit,datum,lon,lat,imagery_only=False):
    if not imagery_only and (unit not in ('m','international foot','US survey foot') or not isinstance(datum,str) or not datum.strip() or datum.upper() in ('UNREVIEWED','UNKNOWN')):
        raise ValueError('Confirm the DEM elevation unit and datum from the source metadata.')
    if not isinstance(files,list) or len(files) not in (2,4):
        raise ValueError('Select a DEM and its receipt, optionally also imagery and its receipt.')
    images={}
    receipts={}
    for entry in files:
        raw=base64.b64decode(entry['content'],validate=True)
        if not raw or len(raw)>15000000:
            raise ValueError('Each archived source must be 1 byte to 15 MB.')
        if Path(entry['name']).suffix.lower()=='.json':
            record=json.loads(raw.decode('utf-8-sig'))
            key='dem' if record.get('mode')=='usgs' and record.get('products') else 'imagery' if record.get('schema_version')=='naip_acquisition_1.0' and record.get('source') else None
            if key=='imagery' and (record.get('status')!='READY_FOR_MAP_REVIEW' or record.get('valid_fraction')!=1):
                raise ValueError('Select a verified NAIP mosaic with full coverage and its original receipt.')
            if not key or key in receipts:
                raise ValueError('Expected distinct 3DEP and optional NAIP acquisition receipts.')
            receipts[key]=(raw,record)
        else:
            images[hashlib.sha256(raw).hexdigest()]=raw
    valid_sources=set(receipts)=={'imagery'} if imagery_only else 'dem' in receipts
    if not valid_sources or len(receipts)*2!=len(files) or len(images)!=len(receipts):
        raise ValueError('Select one receipt and one matching raster for each source.')
    result={}
    for key,(raw,record) in receipts.items():
        raster=images.pop(record['raster']['sha256'],None)
        if raster is None:
            raise ValueError(f'{key}: raster SHA-256 differs from the acquisition receipt.')
        with MemoryFile(raster) as mem,mem.open() as src:
            x,y=Transformer.from_crs(4326,src.crs,always_xy=True).transform(lon,lat)
            row,col=src.index(x,y)
            if src.driver!='GTiff' or not (0<=row<src.height and 0<=col<src.width):
                raise ValueError(f'{key}: the raster does not cover this coordinate.')
        result[key]=(raster,raw,record)
    return result


def install(folder,config,archive,unit,datum):
    dest=folder/'local_terrain'
    dest.mkdir()
    for key,(raster,raw,record) in archive.items():
        path='local_terrain/'+key+'.tif'
        receipt='local_terrain/'+key+'.json'
        (folder/path).write_bytes(raster)
        (folder/receipt).write_bytes(raw)
        if key=='dem':
            config['terrain']=dict(mode='local',raster=path,provenance=receipt,vertical_unit=unit,vertical_datum=datum)
        else:
            config['delivery']['imagery']=dict(raster=path,source=record['source'])
            config['delivery'].setdefault('additional_sources',[]).append(receipt)
