"""Freeze a blind comparison on two surveyed Big River subreaches before reading interior stages."""
import csv
import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from rasterio.io import MemoryFile
from pyproj import Transformer

from ras_workflow import banks
from ras_workflow.common import read, save, sha, item, utc

DATA='https://doi.org/10.5066/P9K3ENAX'
REPORT='https://doi.org/10.3133/sir20225002'
# Upstream to downstream. Figure 3 identifies the direction around each bend.
ANCHORS={'STW':[[707125,4259540],[707108,4259600],[707104,4259660],[707104,4259720],[707111,4259780],[707116,4259840]],
         'PHB':[[708285,4241356],[708316,4241286],[708367,4241169],[708407,4241090],[708499,4241046]]}
EVENTS={'STW':{'20190226':52.4,'20200519':155.},'PHB':{'20181203':29.,'20191106':7.81,'20200320':198.}}
FT=1/.3048
LIMITS=dict(point_ft=1.,mean_ft=.5,refinement_ft=.1,flow_cfs=1.,outlet_ft=.01,independent_locations=2)


def cuts(site, dem):
    nodes=np.array(ANCHORS[site],dtype=float)
    sizes=np.linalg.norm(np.diff(nodes,axis=0),axis=1)
    axis=(nodes[-1]-nodes[0])/np.linalg.norm(nodes[-1]-nodes[0])
    left=np.array([-axis[1],axis[0]])
    centers=[nodes[0]]
    for a,b,length in zip(nodes,nodes[1:],sizes):
        # Keep original location anchors at both levels; coarse spacing <=30 m.
        centers.extend(np.linspace(a,b,2*math.ceil(length/30)+1)[1:])
    chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(centers,axis=0),axis=1))]
    cuts=[]
    offsets=np.arange(-200.,202.,2.)
    for i,center in enumerate(centers):
        xy=center-offsets[:,None]*left
        z=np.array([sample[0] for sample in dem.sample(xy)],dtype=float)
        valid=np.isfinite(z)&(z!=dem.nodata)
        mid=len(z)//2
        if not valid[mid]:
            raise ValueError(f'{site} {i}: survey missing at channel')
        # Keep only the contiguous survey strip on each side of this channel.
        lo=mid
        while lo>0 and valid[lo-1]:lo-=1
        hi=mid+1
        while hi<len(z) and valid[hi]:hi+=1
        pts=xy[lo:hi]
        st=(offsets[lo:hi]-offsets[lo])*FT
        elevations=z[lo:hi]*FT
        row=dict(rs=round(100+(chain[-1]-chain[i])*FT,2),center_xy=center.tolist(),reach_id='river',
                 cutline_xy=pts[[0,-1]].tolist(),station_ft=st.round(5).tolist(),elevation_ft=elevations.round(5).tolist(),
                 expansion_contraction=[.3,.1],local_chainage_ft=chain[i]*FT,
                 reach_length_basis='Along surveyed alignment; equal lengths for the three subdivisions are a screening assumption.')
        # Restrict bank search to the local channel, so a distant floodplain ridge cannot become its bank.
        channel=np.where(abs(offsets[lo:hi])<=65)[0]
        local=dict(row,station_ft=st[channel].tolist(),elevation_ft=elevations[channel].tolist())
        proposal=banks.propose(local)
        indices=proposal.get('selected_indices')
        if indices:
            bank=channel[indices]
        else:
            # Explicit fallback constrained by surveyed bed elevation and the measured plan alignment.
            bed=np.min(elevations[abs(offsets[lo:hi])<=15])
            choices=[]
            for direction in (-1,1):
                candidates=np.where((direction*offsets[lo:hi]>=12)&(direction*offsets[lo:hi]<=65))[0]
                candidates=candidates[np.argsort(abs(offsets[lo:hi][candidates]))]
                rising=candidates[elevations[candidates]>=bed+5]
                if not len(candidates):raise ValueError('Survey does not span both banks')
                choices.append(rising[0] if len(rising) else candidates[np.argmax(elevations[candidates])])
            bank=np.array(choices)
        row['bank_stations_ft']=[row['station_ft'][j] for j in bank]
        row['bank_basis']='DEM break candidates within 65 m of center' if indices else 'Conditional local 5 ft relief fallback within 65 m'
        cuts.append(row)
    return cuts,chain,axis


def geometry(rows, chain):
    cuts=[]
    for i,row in enumerate(rows):
        length=float(chain[i+1]-chain[i])*FT if i+1<len(chain) else 0.
        cuts.append(dict(row,reach_lengths_ft=[length]*3))
    return dict(schema_version='1.0',hydraulic_unit='international_ft',model_type='river',river='Big River',
                channel_geometry_basis='combined_survey_and_dem',vertical_datum='NAVD88',horizontal_crs='EPSG:32615',
                flow_regime='subcritical',cross_sections=cuts,flowlines=[dict(id='river',xy=[r['center_xy'] for r in cuts])],
                structure={},provenance=[DATA,REPORT])


def register_points(xy, sections, axis):
    result=[]
    for i,row in reversed(list(enumerate(sections))):
        if i==0:continue  # Both model end sections excluded from interior checks.
        center=np.asarray(row['center_xy'])
        if result and np.linalg.norm(center-np.array(result[-1]['center_xy']))<50:continue
        offsets=xy-center
        distance=np.linalg.norm(offsets,axis=1)
        along=abs(offsets@axis)
        cut=np.asarray(row['cutline_xy'])
        unit=(cut[1]-cut[0])/np.linalg.norm(cut[1]-cut[0])
        cross=(xy-cut[0])@unit
        candidates=np.where((distance<=35)&(along<=3)&(cross>=0)&(cross<=np.linalg.norm(cut[1]-cut[0])))[0]
        if not len(candidates):
            if i==len(sections)-1:return []
            continue
        j=candidates[np.lexsort((candidates,distance[candidates],along[candidates]))[0]]
        result.append(dict(role='outlet' if i==len(sections)-1 else 'holdout',rs=row['rs'],source_line=int(j)+2,
                           xy=xy[j].tolist(),center_xy=row['center_xy'],normal_offset_m=float(along[j]),from_center_m=float(distance[j])))
    if len({r['source_line'] for r in result})!=len(result):raise ValueError('Duplicate measurement role')
    return result


def published_stage(path,record):
    with path.open(encoding='utf-8-sig',newline='') as source:
        for i,row in enumerate(csv.DictReader(source),2):
            if i==record['source_line']:
                if [float(row[k]) for k in ('X','Y')]!=record['xy']:raise ValueError('Source row moved')
                return float(row['measwse'])*FT
    raise ValueError('No registered source row')


def freeze(raw,out):
    if (out/'protocol.json').exists():
        raise ValueError('Keep the original protocol; use its forecast or score command')
    from ras_workflow.inputs import geometry_errors
    listed=read(Path(__file__).with_name('big_river_sources.json'))['files']
    for source in listed:
        if sha(raw/source['file'])!=source['sha256']:raise ValueError('Changed USGS source '+source['file'])
    out.mkdir(exist_ok=True,parents=True)
    protocol=dict(frozen_utc=utc(),criteria=LIMITS,roughness=dict(channel=.035,overbanks=.065),sites={},
                  data=DATA,flow_reference=REPORT+' Table 4',sources=listed,
                  spatial_rule='Separate centers by >=50 m. Inside cutline, <=3 m normal offset and <=35 m from center. Exclude the upstream end; reserve the downstream end only for boundary.',
                  selection='XY and bed raster only. Rows used by USGS for a separate study. No observed interior elevations used to construct the SteadyReach forecasts.',
                  accuracy='USGS documents RTK-fixed collection but no formal vertical accuracy test. Some water surfaces came from bathymetry or terrestrial lidar processing. Site/event-specific control uncertainty remains open.')
    for site,events in EVENTS.items():
        name=f'BigRiverMO_{site}_dem.tif'
        with ZipFile(raw/(name+'.zip')) as z:
            data=z.read(name)
        with MemoryFile(data) as memory,memory.open() as terrain:
            if terrain.crs.to_epsg()!=32615 or terrain.res!=(2.,2.):raise ValueError('Check horizontal reference and grid resolution')
            rows,chain,axis=cuts(site,terrain)
        dest=out/site;dest.mkdir(exist_ok=True)
        (dest/name).write_bytes(data)
        projected=Transformer.from_crs(32615,4326,always_xy=True)
        info=dict(location=projected.transform(*rows[len(rows)//2]['center_xy']),raster=item(dest/name),levels={},events={})
        for level,step in [('coarse',2),('fine',1)]:
            geom=geometry(rows[::step],chain[::step]);geom['reach']=site
            # The real outlet value is deliberately unavailable at registration.
            check=dict(geom,boundaries={'downstream':dict(type='known_stage',stages_ft=[])})
            errors=[e for e in geometry_errors(check) if e!='Known downstream WSE requires finite elevations in profile order']
            if errors:raise ValueError(errors)
            path=dest/(level+'.json');save(path,geom);info['levels'][level]=item(path)
        for event,q in events.items():
            file=raw/f'BigRiverMO_{site}_{event}_WaterSurfProf.csv'
            xy=np.loadtxt(file,delimiter=',',skiprows=1,usecols=(0,1),ndmin=2)
            info['events'][event]=dict(file=file.name,sha256=sha(file),q_m3s=q,flow_cfs=q*FT**3,
                                       records=register_points(xy,rows[::2],axis))
        protocol['sites'][site]=info
    save(out/'protocol.json',protocol)
    save(out/'registration.json',dict(protocol=item(out/'protocol.json'),registered_utc=utc()))
    for site,info in protocol['sites'].items():
        print(site,{e:len(v['records']) for e,v in info['events'].items()},flush=True)
    return protocol
