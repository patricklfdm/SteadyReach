"""Build a measured-event trial from the Oregon lidar tile and official gage records."""
import argparse
import csv
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ras_workflow.common import read, save, sha
from ras_workflow.river_observations import COLUMNS
from ras_workflow.survey_import import make_manifest

METRES_PER_FOOT = .3048
NOAA = 'https://www.fisheries.noaa.gov/inport/item/62797'
USGS = 'https://api.waterdata.usgs.gov/ogcapi/v0/collections/'
GAUGE = 'USGS-14150000'


def prepare(raw, out):
    out.mkdir(parents=True)

    visits = [f['properties'] for f in read(raw/'measurements.json')['features']
              if f['properties']['monitoring_location_id']==GAUGE and f['properties']['approval_status']=='Approved']
    discharge = min((v for v in visits if v['reading_type']=='Discharge' and v['time'][:10]>'2015-09-15'
                     and any(w['reading_type']=='MeanGageHeight' and w['field_visit_id']==v['field_visit_id'] for w in visits)),
                    key=lambda v:v['time'])
    stage, = [v for v in visits if v['reading_type']=='MeanGageHeight' and v['field_visit_id']==discharge['field_visit_id']]
    site = read(raw/'gage.json')
    lon,lat = site['geometry']['coordinates'][:2]
    gage = site['properties']
    offset = read(raw/'vertcon.json')
    if (gage['vertical_datum'],offset['srcVertDatum'],offset['destVertDatum'],offset['heightUnits'],stage['unit_of_measure'],discharge['unit_of_measure'])!=('NGVD29','NGVD29','NAVD88','m','ft','ft^3/s'):
        raise ValueError('Unexpected gauge, discharge or datum conversion units')
    if abs(float(offset['srcLat'])-lat)>.0001 or abs(float(offset['srcLon'])-lon)>.0001:
        raise ValueError('Wrong datum conversion location')
    zero = gage['altitude']+(float(offset['destOrthoht'])-float(offset['srcOrthoht']))/METRES_PER_FOOT
    pin = np.array(Transformer.from_crs(4326,6339,always_xy=True).transform(lon,lat))
    # Coordinates from the projected terrain map. The middle cut crosses the gage on its right bank.
    offsets = np.array([[215,-173],[162,-130],[112,-90],[60,-50],[0,0],[-60,50],[-117,101],[-176,153],[-229,205]],float)
    center = pin - np.array([50,60])/np.hypot(50,60)*17
    points = center + offsets
    sections=[]
    with rasterio.open(raw/'tb_43122h71.tif') as tile,rasterio.open(raw/'background.tif') as bg:
        if tile.crs.to_epsg()!=6339 or tile.units[0]!='metre' or bg.crs.to_epsg()!=6339:
            raise ValueError('Unexpected coordinate system or lidar units')
        for i,xy in enumerate(points):
            tangent=points[min(i+1,len(points)-1)]-points[max(0,i-1)]
            right=np.array([tangent[1],-tangent[0]])/np.linalg.norm(tangent)
            offsets_m=np.arange(-110,112,2)
            cut=xy+offsets_m[:,None]*right
            profile=np.array([float(v[0]) for v in tile.sample(cut)])
            valid=np.isfinite(profile)&(profile>0)&(profile<1000)
            mid=len(cut)//2
            if not valid[mid]:raise ValueError('Missing lidar at the river center')
            left=next((j+1 for j in range(mid-1,-1,-1) if not valid[j]),0)
            end=next((j for j in range(mid+1,len(cut)) if not valid[j]),len(cut))
            z=profile[left:end]; mid-=left
            stations=(offsets_m[left:end]-offsets_m[left])/METRES_PER_FOOT
            # Interpreted channel boundaries, fixed without reading the event stage.
            bottom=int(np.argmin(z)); bank_height=z[bottom]+2.
            banks=[next((j for j in range(bottom-1,0,-1) if z[j]>=bank_height),1),
                   next((j for j in range(bottom+1,len(z)-1) if z[j]>=bank_height),len(z)-2)]
            length=np.linalg.norm(points[i+1]-xy)/METRES_PER_FOOT if i+1<len(points) else 0
            sections.append(dict(rs=(len(points)-i)*100,center_xy=xy.tolist(),cutline_xy=cut[[left,end-1]].tolist(),
                station_ft=stations.round(4).tolist(),elevation_ft=(z/METRES_PER_FOOT).round(4).tolist(),
                bank_stations_ft=[round(stations[j],4) for j in banks],reach_lengths_ft=[round(float(length),4)]*3,
                expansion_contraction=[.3,.1]))
        # A single endpoint pair is sensitive to pools. Use the reach-wide median
        # of pairwise thalweg gradients as a conditional normal-depth slope.
        chain=np.r_[0,np.cumsum([s['reach_lengths_ft'][1] for s in sections[:-1]])]
        bed=[min(s['elevation_ft']) for s in sections]
        slope=float(np.median([(bed[i]-bed[j])/(chain[j]-chain[i]) for j in range(1,len(bed)) for i in range(j)]))
        if slope<=0:raise ValueError('Review the bed slope and flow direction')
        terrain=bg.read(1)
        lidar=np.full(terrain.shape,-9999,dtype='float32')
        reproject(rasterio.band(tile,1),lidar,dst_crs=bg.crs,dst_transform=bg.transform,dst_nodata=-9999,resampling=Resampling.bilinear)
        valid=lidar!=-9999
        terrain[valid]=lidar[valid]
        with rasterio.open(out/'Terrain.tif','w',**dict(bg.profile,compress='deflate')) as ds:ds.write(terrain,1)
    case='Visit20151001'; date=stage['time'][:10]
    if date!='2015-10-01':raise ValueError('Review a changed field visit record')
    geometry=dict(schema_version='1.0',hydraulic_unit='international_ft',horizontal_crs='EPSG:6339',vertical_datum='NAVD88',
        model_type='river',river='Middle Fork',reach='Dexter',channel_geometry_basis='combined_survey_and_dem',flow_regime='subcritical',
        boundaries=dict(downstream=dict(type='normal_depth')),boundary_slopes=dict(downstream=slope),
        flowlines=[dict(id='river',xy=points.tolist())],cross_sections=sections)
    definition=dict(title='Dexter measured event',location=dict(latitude=lat,longitude=lon),
        terrain=dict(raster='Terrain.tif',vertical_datum='NAVD88',vertical_unit='m'),geometry=geometry,
        scenario=dict(id='dexter',profiles=[dict(id=case,flow_cfs=float(discharge['value']),source='USGS direct discharge, visit '+discharge['field_visit_id'])],
            channel_n=.035,overbank_n=.065,parameter_source='Prespecified assumed roughness. Bank stations and equal overbank lengths interpreted for screening.'))
    save(out/'definition.json',definition)
    save(out/'SourceIndex.json',dict(tile='tb_43122h71.tif',sources={p.name:sha(p) for p in (raw/'tb_43122h71.tif',raw/'background.tif',raw/'measurements.json',raw/'gage.json',raw/'vertcon.json')},
         bank_basis='2 m relief interpreted from lidar; section elevations exclusively from the published interpolated lidar',slope=slope))
    citations={'Terrain.tif':NOAA+' with USGS 3DEP only outside lidar coverage for cartography.','SourceIndex.json':NOAA}
    for name,url in [('measurements.json',USGS+'field-measurements'),('gage.json',USGS+'monitoring-locations'),('vertcon.json','https://geodesy.noaa.gov/web_services/ncat/')]:
        shutil.copyfile(raw/name,out/name);citations[name]=url
    make_manifest(out/'definition.json',[(out/name,url) for name,url in citations.items()])
    returned=out.parent/'event_return.csv'
    with returned.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=(*COLUMNS,'profile'));writer.writeheader()
        writer.writerow(dict(profile=case,event=case,date=date,role='holdout',kind='gage_height',x=lon,y=lat,horizontal_crs='EPSG:4326',
            elevation=stage['value'],unit='ft',vertical_datum='NAVD88',gage_zero=round(zero,6),flow=discharge['value'],flow_unit='cfs',
            source=f"{GAUGE} · {stage['field_visit_id']} · measurements.json, gage.json, vertcon.json. Gage uncertainty unreported."))
    print(case,discharge['value'],stage['value'],zero,slope)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('raw',type=Path);parser.add_argument('out',type=Path)
    args=parser.parse_args();prepare(args.raw,args.out)
