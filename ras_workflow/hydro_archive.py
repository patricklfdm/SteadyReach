"""Extract a small local river window from official USGS HUC8 hydrography downloads."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .common import ROOT, item, read
from .qgis_runtime import environment
from .terrain import fetch


def flowlines(bbox, directory):
    directory.mkdir(parents=True, exist_ok=True)
    qgis, env=environment()
    program=qgis/'bin/ogr2ogr.exe'
    if not program.is_file():
        raise ValueError('The local QGIS GDAL tools are required for the USGS subbasin download fallback')
    url='https://tnmaccess.nationalmap.gov/api/v1/products?'+urlencode(dict(
        datasets='National Hydrography Dataset (NHD) Best Resolution',bbox=','.join(f'{x:.5f}' for x in bbox),max=100))
    catalog=directory/'catalog.json'
    fetch(url,catalog,5_000_000)
    data=read(catalog)
    if data.get('total',0)>len(data.get('items',[])):
        raise ValueError('Hydrography catalog response is incomplete')
    products={p['downloadURL']:p for p in data['items'] if '/HU8/GPKG/' in p.get('downloadURL','')}
    budget=75_000_000
    if not products or len(products)>4 or sum(p.get('sizeInBytes') or budget+1 for p in products.values())>budget:
        raise ValueError('No complete set of HUC8 GeoPackages within the 75 MB hydrography download limit')
    records=[dict(**item(catalog,'USGS_HUC8_catalog'),url=url)]
    features={}
    for url, product in sorted(products.items()):
        name=Path(urlsplit(url).path).name
        archive=directory/name
        receipt=fetch(url,archive,budget);budget-=receipt['size_bytes']
        records.append(dict(**item(archive,'USGS_HUC8_archive'),url=url,product_id=product['sourceId']))
        if not zipfile.is_zipfile(archive):
            raise ValueError('USGS subbasin download is not a readable ZIP')
        with zipfile.ZipFile(archive) as z:
            members=[i for i in z.infolist() if i.filename.lower().endswith('.gpkg')]
            if len(members)!=1 or members[0].file_size>400_000_000:
                raise ValueError('Unexpected USGS subbasin GeoPackage contents')
            gpkg=archive.with_suffix('.gpkg')
            with z.open(members[0]) as src,gpkg.open('wb') as dest:
                shutil.copyfileobj(src,dest,1024*1024)
        output=archive.with_suffix('.geojson')
        cmd=[str(program),'-f','GeoJSON','-spat',*map(str,bbox),'-spat_srs','EPSG:4326',
             '-t_srs','EPSG:4326','-where','FType IN (460,558)',str(output),str(gpkg),'NHDFlowline']
        try:
            proc=subprocess.run(cmd,env=env,capture_output=True,timeout=75,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as error:
            raise ValueError('USGS local flowline extraction exceeded the 75 second limit') from error
        if proc.returncode:
            raise ValueError('GDAL hydrography extraction failed: '+proc.stderr.decode(errors='replace')[-450:])
        records.append(item(output,'USGS_flowlines_in_study_area'))
        for feature in read(output)['features']:
            attrs={k.lower():v for k,v in feature['properties'].items()}
            # USGS GeoPackages use Permanent_Identifier or Permanent_ while
            # Esri services expose permanent_identifier.
            key=attrs.get('permanent_identifier') or attrs.get('permanent_')
            if not key:
                raise ValueError('USGS flowline identifier missing')
            attrs['permanent_identifier']=key
            geom=feature['geometry'];coords=geom['coordinates']
            if geom['type'] not in ('LineString','MultiLineString'):
                raise ValueError('Unsupported hydrography geometry')
            features[key]=dict(attributes=attrs,geometry=dict(paths=[coords] if geom['type']=='LineString' else coords))
    return list(features.values()),records
