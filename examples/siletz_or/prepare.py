"""Prepare the independent Siletz benchmark from the cited public USGS releases."""
import argparse
import csv
from datetime import datetime, timedelta
import io
from pathlib import Path
import shutil
from statistics import median
import sys
from zipfile import ZipFile

import h5py
import numpy as np
from pyproj import CRS, Transformer

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ras_workflow.common import save, sha
from ras_workflow.public_reach import road_crossings
from ras_workflow.survey_import import make_manifest

OUTLET, INTERIOR = '986237', '9695486'
if __package__:
    from .discharge import URL, V1_NAME, archived_input, obtain, read_discharge
else:
    from discharge import URL, V1_NAME, archived_input, obtain, read_discharge
MODEL = 'https://doi.org/10.5066/P1489NN8'
STAGE = 'https://doi.org/10.5066/P1N35MQN'
CONTEXT_URL = ('https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'
               '?bbox=433000,4951300,437100,4955500&bboxSR=26910&imageSR=26910&size=683,700&format=tiff'
               '&pixelType=F32&interpolation=RSP_Bilinear&renderingRule=%7B%22rasterFunction%22%3A%22None%22%7D&f=image')


def select_events(folder,ratio,flow_file=None):
    path=flow_file or archived_input(folder)
    if not path:raise ValueError('Missing frozen USGS discharge source')
    entries=read_discharge(path)
    with (folder/'Calculated Data.csv').open(encoding='utf-8-sig') as handle:
        stages={datetime.strptime(r['Date Time'],'%m/%d/%Y %H:%M'):r for r in csv.DictReader(handle)}
    sites={r[0]:float(r[6]) for r in list(csv.reader((folder/'Site Information.csv').read_text('cp1252').replace('\xa0','').splitlines()))[1:] if r[0] in (OUTLET,INTERIOR)}
    result=[]
    for name,start,end,low,high in [('Dev','2017-11-01','2018-01-01',600,1800),('Holdout','2018-01-01','2018-03-01',2200,3600)]:
        for time in sorted(entries):
            if not start<=time.date().isoformat()<end or (time.hour,time.minute)!=(12,0):continue
            try:
                flow=[entries[time+timedelta(minutes=i*15)] for i in range(-24,25)]
                readings={sensor:[float(stages[time+timedelta(minutes=i*30)][sensor]) for i in range(-12,13)]
                          for sensor in (OUTLET,INTERIOR)}
            except (ValueError,KeyError):continue
            q=median(flow)
            if not low<=q<=high or max(flow)-min(flow)>.03*q or any(min(vals)<=sites[k] for k,vals in readings.items()):continue
            result.append(dict(id=name,date=time.date().isoformat(),gage_cfs=q,reach_cfs=q*ratio,transfer_ratio=ratio,
                gage_range_cfs=[min(flow),max(flow)],samples_flow=len(flow),samples_stage=len(readings[OUTLET]),
                stage_m={k:median(v) for k,v in readings.items()},stage_range_m={k:[min(v),max(v)] for k,v in readings.items()}))
            break
        else:raise ValueError('No event meets the preregistered rules for '+name)
    return result


def published_flows(flow_lines):
    values={}
    for line,following in zip(flow_lines,flow_lines[1:]):
        if line.startswith('River Rch & RM='):
            values[int(line.rsplit(',',1)[1])]=float(following[16:24])
    return values


def section_inputs(folder):
    def member(archive,ending):
        return archive.read(next(n for n in archive.namelist() if n.endswith(ending)))
    with ZipFile(folder/'Siletz_1D_Model.zip') as archive:
        source_crs=CRS.from_wkt(member(archive,'Projection.prj').decode())
        geom_raw=member(archive,'FINAL.g01.hdf')
        flow_lines=member(archive,'FINAL.f01').decode().splitlines()
    values=published_flows(flow_lines)
    ratio=values[44506]/values[19532]
    to_utm=Transformer.from_crs(source_crs,26910,always_xy=True)
    with h5py.File(io.BytesIO(geom_raw)) as h:
        g=h['Geometry/Cross Sections'];channel=h['Geometry/River Centerlines/Polyline Points'][:]
        sections=[];chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(channel,axis=0),axis=1))]
        chainages=[]
        for a,poly,zinfo in zip(g['Attributes'][:],g['Polyline Info'][:],g['Station Elevation Info'][:],strict=True):
            rs=float(a['RS'])
            if not 34913<=rs<=44506:continue
            i,n=poly[:2];cut=g['Polyline Points'][i:i+n]
            hits=road_crossings(channel,[({'NAME':'section'},cut)])
            if len(hits)!=1:raise ValueError(f'Expected one centerline intersection at {rs}')
            at=hits[0][0];chainages.append(at)
            center=[np.interp(at,chain,col) for col in channel.T]
            start,count=zinfo
            points=g['Station Elevation Values'][start:start+count].astype(float)
            banks=[round(float(a[k]),3) for k in ('Left Bank','Right Bank')]
            if not np.all(np.diff(points[:,0])>0):raise ValueError(f'Duplicate section station at {rs}')
            stations=np.unique(np.r_[points[:,0].round(3),banks])
            sections.append(dict(rs=rs,center_xy=list(to_utm.transform(*center)),cutline_xy=np.column_stack(to_utm.transform(*cut.T)).tolist(),
                station_ft=stations.tolist(),elevation_ft=np.interp(stations,*points.T).round(4).tolist(),
                bank_stations_ft=banks,reach_lengths_ft=[float(a[k]) for k in ('Len Left','Len Channel','Len Right')],
                expansion_contraction=[float(a['Expan']),float(a['Contr'])]))
        if any(int(s['RS']) in range(34913,44507) for s in h['Geometry/Structures/Attributes'][:]):
            raise ValueError('A structure lies within the chosen reach')
        if set(values).intersection(range(34914,44506)):raise ValueError('An internal discharge change requires a different reach')
        if sorted(chainages)!=chainages:raise ValueError('Check survey centerline direction')
        inside=channel[(chain>chainages[0]) & (chain<chainages[-1])]
        path=[sections[0]['center_xy'],*np.column_stack(to_utm.transform(*inside.T)).tolist(),sections[-1]['center_xy']]
        sections[-1]['reach_lengths_ft']=[0,0,0]
    return sections,path,ratio


def prepare(source,terrain,out,profile=None,context=None):
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, Resampling
    sections,xy,ratio=section_inputs(source)
    out.mkdir(parents=True,exist_ok=False)
    flow_file=archived_input(source) or obtain(out)
    all_events=select_events(source,ratio,flow_file)
    events=[r for r in all_events if profile is None or r['id']==profile]
    points=np.concatenate([s['cutline_xy'] for s in sections])
    lo=points.min(axis=0)-30;hi=points.max(axis=0)+30
    shape=np.ceil((hi-lo)/3).astype(int)
    transform=from_origin(lo[0],hi[1],3,3)
    raster=out/'SiletzTerrain.tif'
    if context:
        center=(hi+lo)/2
        half=max(hi-lo)*.60
        lo,hi=center-half,center+half
        shape=np.ceil((hi-lo)/3).astype(int)
        transform=from_origin(lo[0],hi[1],3,3)
    with rasterio.open(terrain) as src, rasterio.open(raster,'w',driver='GTiff',width=shape[0],height=shape[1],
            count=1,dtype='float32',crs='EPSG:26910',transform=transform,nodata=-9999,compress='deflate') as dst:
        def warp(ds):
            array=np.full((shape[1],shape[0]),-9999,dtype='float32')
            reproject(rasterio.band(ds,1),array,dst_crs='EPSG:26910',dst_transform=transform,
                      dst_nodata=-9999,resampling=Resampling.bilinear)
            return array
        data=warp(src)
        if context:
            with rasterio.open(context) as ds:
                if ds.crs.to_epsg()!=26910:raise ValueError('Use the cited NAD83 UTM 10N context raster')
                background=warp(ds)
            missing=data==-9999
            if np.any(background[missing]==-9999):raise ValueError('Missing background DEM in exhibit extent')
            data[missing]=background[missing]/.3048
        dst.write(data,1)
    project=Transformer.from_crs(26910,4326,always_xy=True)
    lon,lat=project.transform(*sections[len(sections)//2]['center_xy'])
    geom=dict(schema_version='1.0',hydraulic_unit='international_ft',horizontal_crs='EPSG:26910',vertical_datum='NAVD88',
            model_type='river',river='Siletz',reach='PT reach',channel_geometry_basis='combined_survey_and_dem',
            flow_regime='subcritical',boundaries={'downstream':dict(type='known_stage',stages_ft=[r['stage_m'][OUTLET]/.3048 for r in events])},
            boundary_slopes={},flowlines=[dict(id='river',xy=xy)],cross_sections=sections)
    profiles=[dict(id=r['id'],flow_cfs=r['reach_cfs'],source='USGS 14305500 observed +/-6h median on '+r['date']+
                   ' times the published Table 14 reach/gage ratio; conditional ungaged transfer.') for r in events]
    config=dict(title='Siletz measured steady events',location=dict(latitude=lat,longitude=lon),
                terrain=dict(raster=raster.name,vertical_datum='NAVD88',vertical_unit='international foot'),
                geometry=geom,scenario=dict(id='siletz',profiles=profiles,channel_n=.035,overbank_n=.065,
                     parameter_source='Fixed benchmark assumptions before stage comparison; within USGS SIR 2025-5063 ranges.'))
    definition=out/'definition.json';save(definition,config)
    citations=dict([(raster.name,MODEL+'; crop of USGS published model terrain, elevations in feet NAVD88, resampled to UTM 10N at 3 m.'),
        ('Calculated Data.csv',STAGE),('Site Information.csv',STAGE),(flow_file.name,URL if flow_file.name==V1_NAME else 'Archived USGS WaterServices RDB, station 14305500, approved discharge in cfs'),
        ('Siletz River Surface Water Elevation.xml',STAGE),('geometry_inputs.hdf',MODEL+'; original g01 geometry only.'),
        ('flow_inputs.f01',MODEL+'; Table 14 flow-change cards for discharge transfer.'),
        ('protocol.json','Frozen evaluation and selection criteria for the two events.'),
        ('events.json','Observed event window statistics, discharge transfer and source file fingerprints.')])
    with ZipFile(source/'Siletz_1D_Model.zip') as archive:
        for filename,extension in [('geometry_inputs.hdf','FINAL.g01.hdf'),('flow_inputs.f01','FINAL.f01')]:
            (out/filename).write_bytes(archive.read(next(n for n in archive.namelist() if n.endswith(extension))))
    if context:
        citations['background_m.tif']=CONTEXT_URL+'; current 3DEP topography in metres NAVD88; map gaps only.'
        citations[raster.name]+=' Released terrain takes precedence; only NoData areas filled from 3DEP after metre-to-foot conversion. Survey hydraulic sections are unchanged.'
        shutil.copyfile(context,out/'background_m.tif')
    if flow_file.parent!=out:shutil.copyfile(flow_file,out/flow_file.name)
    for filename in ('Calculated Data.csv','Site Information.csv','Siletz River Surface Water Elevation.xml'):
        shutil.copyfile(source/filename,out/filename)
    shutil.copyfile(Path(__file__).with_name('protocol.json'),out/'protocol.json')
    save(out/'events.json',dict(events=all_events,included_profiles=[r['id'] for r in events],terrain_source_sha256=sha(terrain),model_archive_sha256=sha(source/'Siletz_1D_Model.zip'),
         original_inputs={name:sha(out/name) for name in citations if name!='events.json'}))
    manifest=make_manifest(definition,[(out/n,c) for n,c in citations.items()])
    print(manifest)


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    for arg in ('source','terrain','out'):cli.add_argument(arg,type=Path)
    cli.add_argument('--profile',choices=['Dev','Holdout'],help='Isolate one frozen event without changing the selection or model inputs')
    cli.add_argument('--context',type=Path,help='Optional cited USGS background mosaic in metres for the square print layout')
    args=cli.parse_args()
    prepare(args.source,args.terrain,args.out,args.profile,args.context)
