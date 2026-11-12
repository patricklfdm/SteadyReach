"""External cross-section drafts from an explicitly oriented reviewed flowline.
No buried structure, bank, or hydraulic boundary is silently filled.
"""
import csv
import numpy as np
import rasterio
from pyproj import CRS
from .common import *

from .geometry_qa import intersects as intersect

def draft(project_path,alignment_path):
    path=safe_path(ROOT,project_path);config=read(path);ap=safe_path(path.parent,alignment_path);spec=read(ap)
    t=config['terrain']
    if t.get('mode')!='local':raise ValueError('Promote and explicitly label a reviewed downloaded raster as local before sampling')
    units={'m':1/.3048,'international foot':1,'US survey foot':(1200/3937)/.3048}
    if t.get('vertical_unit') not in units or not t.get('vertical_datum'):raise ValueError('Explicit reviewed vertical metadata required')
    if not spec.get('reviewed_upstream_to_downstream'):raise ValueError('Flow direction/alignment review is required')
    xy=np.asarray(spec['flowline_xy'],dtype=float)
    if len(xy)<2 or not np.isfinite(xy).all():raise ValueError('Invalid flowline')
    with rasterio.open(safe_path(path.parent,t['raster'])) as dem:
        crs=CRS.from_wkt(dem.crs.to_wkt())
        crs=crs.sub_crs_list[0] if crs.is_compound else crs
        if not crs.is_projected or not crs.equals(CRS.from_user_input(spec['crs'])):raise ValueError('Flowline and DEM CRS must agree exactly')
        unit_ft=crs.axis_info[0].unit_conversion_factor/.3048
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        if (np.diff(distances)<=0).any():raise ValueError('Duplicate flowline vertices')
        positions=np.asarray(spec['chainages_ft'],dtype=float)/unit_ft
        if not np.all(np.diff(positions)>0) or positions[0]<0 or positions[-1]>distances[-1]:raise ValueError('Chainages must increase downstream within flowline')
        cuts=[];rows=[]
        for i,pos in enumerate(positions):
            seg=min(len(xy)-2,np.searchsorted(distances,pos,side='right')-1)
            delta=xy[seg+1]-xy[seg];direction=delta/np.linalg.norm(delta)
            center=xy[seg]+direction*(pos-distances[seg]);left=np.array([-direction[1],direction[0]])
            width=spec['width_ft'];step=spec['sampling_ft']
            if not (finite(width) and width>0 and finite(step) and 0<step<=width/2):raise ValueError('Explicit positive width and sampling interval required')
            stations=np.linspace(0,width,math.ceil(width/step)+1)
            points=center+(width/2-stations)[:,None]/unit_ft*left
            values=np.ma.vstack(list(dem.sample(points,masked=True)))[:,0]
            if np.ma.getmaskarray(values).any() or not np.isfinite(values.data).all():raise ValueError('Cross section intersects NoData; no interpolation across gaps')
            z=values.data.astype(float)*units[t['vertical_unit']]
            cut=np.array([points[0],points[-1]]);cuts.append(cut)
            rows.append(dict(rs=round((distances[-1]-pos)*unit_ft,2),center_xy=center.tolist(),cutline_xy=cut.tolist(),station_ft=stations.tolist(),elevation_ft=z.tolist(),
                bank_stations_ft=None,reach_lengths_ft=None,expansion_contraction=None,review_status='DRAFT_REQUIRES_REVIEW',
                channel_distance_to_next_ft=float((positions[i+1]-pos)*unit_ft) if i+1<len(positions) else 0,
                note='Main channel distance follows supplied flowline; separate LOB/ROB flow lengths still required'))
    crossings=[(i,j) for i in range(len(cuts)) for j in range(i+1,len(cuts)) if intersect(*cuts[i],*cuts[j])]
    folder=path.parent/'section_drafts'/unique_id();folder.mkdir(parents=True)
    result=dict(status='REVIEW_REQUIRED',cross_sections=rows,intersecting_cutlines=crossings,
        provenance=[item(ap,'reviewed_flowline'),item(safe_path(path.parent,t['raster']),'external_DEM')],
        vertical_datum=t['vertical_datum'],hydraulic_unit='international_ft',horizontal_crs=crs.to_wkt(),
        limitations=['Banks, overbank reach lengths, functional section locations and bypass paths require review',
            'No structure geometry or downstream slope inferred','NoData forbidden; negative elevations valid',
            'Local flowline normals can intersect at bends; inspect reported intersections before modelling'])
    from .banks import annotate
    annotate(result,spec.get('bank_screening'))
    save(folder/'draft.json',result)
    # RFC7946 GeoJSON requires WGS84, so explicitly transform geometry for portable viewing.
    from pyproj import Transformer
    tr=Transformer.from_crs(crs,4326,always_xy=True)
    features=[dict(type='Feature',properties=dict(rs=r['rs'],status='DRAFT'),geometry=dict(type='LineString',coordinates=[list(tr.transform(*p)) for p in r['cutline_xy']])) for r in rows]
    save(folder/'cutlines.geojson',dict(type='FeatureCollection',features=features))
    with (folder/'sections.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['rs','station_ft','elevation_ft','datum'])
        for r in rows:w.writerows([r['rs'],x,z,t['vertical_datum']] for x,z in zip(r['station_ft'],r['elevation_ft']))
    print(rel(folder));return result
