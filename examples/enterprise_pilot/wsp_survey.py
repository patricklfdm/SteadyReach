"""Prepare the USGS Big River Washington State Park event from its public survey releases."""
import argparse
import csv
from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

import numpy as np
import rasterio
from pyproj import Transformer

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'ras_workflow').is_dir())
sys.path.insert(0,str(ROOT))
from ras_workflow import banks,inputs,river_observations
from ras_workflow.common import save,sha

DATA='https://doi.org/10.5066/P9K3ENAX'
REPORT='https://doi.org/10.3133/sir20225002'
METERS_TO_FT=1/.3048
EVENT='BigRiverMO_WSP_20190206_WaterSurfProf.csv'
DEM='BigRiverMO_WSP_dem.tif'


def prepare(raw,out):
    manifest = json.loads(Path(__file__).with_name('source_hashes.json').read_text(encoding='utf-8'))
    for name in (DEM+'.zip', EVENT, 'BigRiverMO_dem.xml', 'BigRiverMO_WaterSurfProf.xml', 'table3.txt'):
        if sha(raw/name) != manifest[name]:
            raise ValueError('Survey source differs from the registered file: '+name)
    out.mkdir(exist_ok=False,parents=True)
    survey=out/'survey';survey.mkdir()
    with ZipFile(raw/(DEM+'.zip')) as archive:
        with archive.open(DEM) as source,(survey/DEM).open('xb') as target:
            shutil.copyfileobj(source,target)
    points=np.loadtxt(raw/EVENT,skiprows=1,delimiter=',')
    if np.median(points[-15:,2])<=np.median(points[:15,2]):
        raise ValueError('Recheck the published upstream/downstream ordering')
    xy=points[::-1,:2]
    chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    def point(s):
        return np.array([np.interp(s,chain,xy[:,k]) for k in (0,1)])
    def curvature(s):
        start=point(s);chord=point(s+240)-start
        nodes=np.array([point(v) for v in np.linspace(s,s+240,61)])-start
        return np.max(np.abs(nodes[:,0]*chord[1]-nodes[:,1]*chord[0]))/np.linalg.norm(chord)
    start=min(np.arange(np.ceil(.1*chain[-1]),np.floor(.9*chain[-1])-240+1,2),key=curvature)
    axis=point(start+240)-point(start);axis/=np.linalg.norm(axis)
    left=np.array([-axis[1],axis[0]])
    cuts=[];marks=[]
    with rasterio.open(survey/DEM) as terrain:
        if terrain.crs.to_epsg()!=32615:raise ValueError('Unexpected horizontal reference')
        for i,center_at in enumerate(np.linspace(start,start+240,9)):
            center=point(center_at);offset=np.arange(-120,121,2)
            section=center-offset[:,None]*left
            z=np.array([v[0] for v in terrain.sample(section)])
            valid=np.isfinite(z)&(z!=terrain.nodata)
            if not valid[60] or not valid[np.where(valid)[0][0]:np.where(valid)[0][-1]+1].all():
                raise ValueError('Missing surveyed elevations inside section '+str(i))
            xy_cut=section[valid];sta=(offset[valid]-offset[valid][0])*METERS_TO_FT
            row=dict(rs=(9-i)*100,center_xy=center.tolist(),cutline_xy=xy_cut[[0,-1]].tolist(),
                     station_ft=sta.round(6).tolist(),elevation_ft=(z[valid].astype(float)*METERS_TO_FT).round(6).tolist(),
                     reach_lengths_ft=[30*METERS_TO_FT if i<8 else 0.]*3,reach_id='river',
                     local_chainage_ft=(center_at-start)*METERS_TO_FT,expansion_contraction=[.3,.1],
                     reach_length_basis='Parallel cuts spaced 30 m along the measured flow path; overbank flow path assumed equal.')
            proposal=banks.propose(row)
            if not proposal['selected_indices']:raise ValueError('Bank estimation requires review at '+str(row['rs']))
            row['bank_stations_ft']=[row['station_ft'][j] for j in proposal['selected_indices']]
            cuts.append(row)
            nearest=int(np.argmin(np.linalg.norm(points[:,:2]-center,axis=1)))
            if np.linalg.norm(points[nearest,:2]-center)>5:raise ValueError('No admissible field station')
            marks.append((row['rs'],nearest,points[nearest]))
    geometry=dict(schema_version='1.0',hydraulic_unit='international_ft',model_type='river',river='Big River',reach='Washington SP',
        channel_geometry_basis='combined_survey_and_dem',vertical_datum='NAVD88',horizontal_crs='EPSG:32615',flow_regime='subcritical',
        cross_sections=cuts,flowlines=[dict(id='river',xy=[point(s).tolist() for s in np.linspace(start-10,start+250,100)])],
        boundaries={'downstream':dict(type='known_stage',stages_ft=[float(marks[-1][2][2]*METERS_TO_FT)])},
        structure={},provenance=[DATA,REPORT])
    errors=inputs.geometry_errors(geometry)
    if errors:raise ValueError(errors)
    lon,lat=Transformer.from_crs(32615,4326,always_xy=True).transform(*cuts[4]['center_xy'])
    refs=[]
    for file in (DEM,'BigRiverMO_dem.xml','BigRiverMO_WaterSurfProf.xml'):
        if file!=DEM:shutil.copy2(raw/file,survey/file)
        refs.append(dict(name=file,source=DATA,sha256=sha(survey/file)))
    # The original table also contains observed slopes and the USGS model's RMSE.
    # Supply only the measured date, discharge and measurement type to the baseline.
    current=None;selected=[]
    for line in (raw/'table3.txt').read_text(encoding='utf-8-sig').splitlines()[1:]:
        fields=line.replace('–','-').split()
        if not fields:continue
        if fields[0].isalpha():current=fields.pop(0)
        if current=='WSP' and fields[0]=='2019-02-06':selected.append(fields)
    if len(selected)!=1 or selected[0][1:3]!=['41.0','DP']:raise ValueError('Published discharge row differs')
    discharge_ref=survey/'Discharge.json'
    save(discharge_ref,dict(reach='WSP',date=selected[0][0],flow_m3s=float(selected[0][1]),measurement_type=selected[0][2],
        provider=REPORT,original_sha256=sha(raw/'table3.txt')))
    refs.append(dict(name=discharge_ref.name,source=REPORT+' WSP discharge row, 2019-02-06',sha256=sha(discharge_ref)))
    discharge=float(selected[0][1])*METERS_TO_FT**3
    packet=dict(schema_version='steadyreach_survey_1',title='Big River at Washington State Park, Missouri',
        location=dict(latitude=lat,longitude=lon),scenario=dict(id='wsp_feb06',profiles=[dict(id='Feb06',flow_cfs=discharge,source=REPORT+' WSP direct measurement, 2019-02-06.')],
        channel_n=.035,overbank_n=.065,parameter_source='Conditional screening assumptions before native runs. DEM-interpreted banks and constant roughness require engineering review.'),
        geometry=geometry,terrain=dict(raster=DEM,vertical_datum='NAVD88',vertical_unit='m'),files=refs)
    shutil.copy2(raw/EVENT,out/EVENT)
    for boundary,destination in [(True,survey/'observed_profiles.csv'),(False,out/'field_return.csv')]:
        with destination.open('w',newline='',encoding='utf-8') as file:
            writer=csv.DictWriter(file,fieldnames=['profile',*river_observations.COLUMNS]);writer.writeheader()
            for station,j,p in marks:
                if (station==100)!=boundary:continue
                writer.writerow(dict(profile='Feb06',event='Feb06',date='2019-02-06',role='boundary' if boundary else 'holdout',
                    kind='boundary_stage' if boundary else 'stage',x=p[0],y=p[1],horizontal_crs='EPSG:32615',vertical_datum='NAVD88',
                    elevation=p[2],unit='m',flow=41.,flow_unit='m3/s',source=DATA+' '+EVENT+' row '+str(j+2)))
    refs.append(dict(name='observed_profiles.csv',source=DATA+' measured outlet row only, 2019-02-06',
                     sha256=sha(survey/'observed_profiles.csv')))
    save(survey/'survey.json',packet)
    save(out/'preparation.json',dict(discharge_cfs=discharge,sections=9,original_sha256=sha(raw/EVENT),
         raster_sha256=sha(survey/DEM),packet_sha256=sha(survey/'survey.json'),field_sha256=sha(out/'field_return.csv'),
         origin_m=start,coordinate_order='downstream from higher end of released profile',
         assumptions=['Section bank positions','Uniform subdivision reach lengths','Roughness'],field_uncertainty_ft=None))
    print(survey)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('raw',type=Path);cli.add_argument('output',type=Path)
    args=cli.parse_args();prepare(args.raw,args.output)
