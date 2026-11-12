"""Compare a reviewed section profile with DEM samples along its GIS cutline.

Fractional station mapping is explicit. This is a terrain discrepancy check,
not survey calibration, a bank approval, or a replacement hydraulic model.
"""
import numpy as np
import rasterio
from pyproj import CRS,Transformer
from .common import ROOT,intact,item,read,safe_path,save,utc

def compare(project_path,geometry_path,output):
    project_path=safe_path(ROOT,project_path);gp=safe_path(ROOT,geometry_path)
    c=read(project_path);g=read(gp);t=c['terrain'];units={'m':1/.3048,'international foot':1.,'US survey foot':(1200/3937)/.3048}
    if g.get('hydraulic_unit')!='international_ft' or t.get('vertical_unit') not in units or not t.get('vertical_datum') or t['vertical_datum']!=g.get('vertical_datum'):raise ValueError('Explicit matching vertical datum and supported units required; no vertical transform is inferred')
    if not g.get('provenance'):raise ValueError('Reference geometry needs provenance')
    raster=safe_path(project_path.parent,t['raster']);out=safe_path(ROOT,output)
    evidence=[e for e in g['provenance'] if isinstance(e,dict) and 'sha256' in e] if isinstance(g['provenance'],list) else []
    if evidence and not intact(evidence):raise ValueError('Reference source evidence changed')
    if t.get('provenance'):evidence.append(item(safe_path(project_path.parent,t['provenance'])))
    if out.exists():raise ValueError('Use a new comparison directory')
    out.mkdir(parents=True)
    from .report_data import plot_style
    plt=plot_style();rows=[]
    with rasterio.open(raster) as dem:
        target=CRS.from_user_input(dem.crs);target=target.sub_crs_list[0] if target.is_compound else target
        source=CRS.from_user_input(g['horizontal_crs'])
        if not source.is_projected or not target.is_projected:raise ValueError('Projected coordinate systems required')
        transformer=Transformer.from_crs(source,target,always_xy=True)
        for i,r in enumerate(g['cross_sections']):
            a=np.asarray(r['station_ft'],float);z=np.asarray(r['elevation_ft'],float);cut=np.asarray(r['cutline_xy'],float)
            distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(cut,axis=0),axis=1))]
            if len(a)<3 or len(a)!=len(z) or not np.isfinite(np.r_[a,z,cut.ravel()]).all() or not (np.diff(a)>0).all() or not (np.diff(distance)>0).all():raise ValueError('Invalid source section arrays')
            pos=(a-a[0])/(a[-1]-a[0])*distance[-1]
            x,y=transformer.transform(np.interp(pos,distance,cut[:,0]),np.interp(pos,distance,cut[:,1]))
            values=np.ma.vstack(list(dem.sample(list(zip(x,y)),masked=True)))[:,0];valid=~np.ma.getmaskarray(values)&np.isfinite(values.data)
            zz=values.data.astype(float)*units[t['vertical_unit']];delta=zz[valid]-z[valid]
            row=dict(rs=r['rs'],valid_samples=int(valid.sum()),missing_samples=int((~valid).sum()),
                mean_delta_ft=float(delta.mean()) if len(delta) else None,rmse_ft=float(np.sqrt((delta**2).mean())) if len(delta) else None,max_abs_delta_ft=float(np.abs(delta).max()) if len(delta) else None,
                station_ft=a.tolist(),reference_elevation_ft=z.tolist(),dem_elevation_ft=[float(v) if ok else None for v,ok in zip(zz,valid)],status='REVIEW_REQUIRED')
            fig,ax=plt.subplots(figsize=(8,3.4));ax.plot(a,z,label='Reviewed reference geometry');ax.plot(a,np.where(valid,zz,np.nan),label='USGS DEM samples');ax.set(xlabel='Station (international ft)',ylabel='Elevation (international ft)',title='RS '+str(r['rs'])+' / '+g['vertical_datum']);ax.grid(alpha=.2);ax.legend();fig.tight_layout();p=out/f'section_{i+1}.png';fig.savefig(p,dpi=150);plt.close(fig);row['figure']=item(p);rows.append(row)
    result=dict(schema_version='terrain_reference_comparison_1.0',created_utc=utc(),status='REVIEW_REQUIRED',sources=[item(project_path),item(gp),item(raster)]+evidence,rows=rows,
        station_mapping='Fraction of source station extent along GIS cutline length; not independently surveyed sample geolocation',vertical_datum=g['vertical_datum'],unit='international ft',new_solver_calls=0,
        limitations=['NoData remains null; no interpolation across gaps','CRS realization and station-to-GIS correspondence require review','DEM cannot supply buried culvert geometry','Terrain/survey disagreement is not a measured hydraulic error'],engineering_acceptance='NOT_ASSESSED')
    save(out/'comparison.json',result);return result
