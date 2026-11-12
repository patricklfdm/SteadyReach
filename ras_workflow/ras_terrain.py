"""Actual RasProcess terrain creation; units are explicit, datum is unchanged."""
import subprocess
import rasterio, numpy as np, h5py
from pyproj import CRS
from .common import *

def create(path,c,engine,folder):
    t=c['terrain'];factor={'m':1/.3048,'US survey foot':(1200/3937)/.3048,'international foot':1}.get(t.get('vertical_unit'))
    if factor is None or not t.get('vertical_datum'):raise ValueError('Native terrain requires reviewed vertical units and datum')
    source=safe_path(path.parent,t['raster']);dest=folder/'hydraulic_ft.tif';projection=folder/'horizontal.prj'
    with rasterio.open(source) as src:
        crs=CRS.from_wkt(src.crs.to_wkt());horizontal=crs.sub_crs_list[0] if crs.is_compound else crs
        if not horizontal.is_projected:raise ValueError('Native terrain requires a projected raster')
        profile=src.profile.copy();profile.update(crs=horizontal.to_wkt(),dtype='float32')
        with rasterio.open(dest,'w',**profile) as out:
            for _,w in src.block_windows(1):
                z=src.read(1,window=w,masked=True);a=z.data.copy();valid=~np.ma.getmaskarray(z)&np.isfinite(a)
                a[valid]=(a[valid].astype(float)*factor).astype('float32');out.write(a,1,window=w)
            out.update_tags(VERTICAL_UNIT='international foot',VERTICAL_DATUM=t['vertical_datum'],PROVENANCE='Vertical units only; no datum transformation')
        projection.write_text(horizontal.to_wkt(version='WKT1_ESRI'),encoding='utf-8')
    native=folder/'Terrain';native.mkdir();hdf=native/'Native.hdf';exe=Path(engine['selected']['executable']).parent/'RasProcess.exe'
    args=[str(exe),'CreateTerrain','units=Feet','stitch=false','prj='+str(projection),'out='+str(hdf),str(dest)]
    start=utc();r=subprocess.run(args,cwd=folder,capture_output=True,timeout=180)
    (folder/'stdout.log').write_bytes(r.stdout);(folder/'stderr.log').write_bytes(r.stderr)
    if r.returncode or not hdf.is_file():raise RuntimeError('Actual RasProcess terrain failed')
    with h5py.File(hdf) as f:attrs={k:repr(v) for k,v in f.attrs.items()}
    rec=dict(status='READY',started_at_utc=start,finished_at_utc=utc(),executable=str(exe),executable_sha256=sha(exe),args=args,returncode=r.returncode,
        source=item(source),unit_factor=factor,vertical_datum_changed=False,vertical_datum=t['vertical_datum'],hdf_attributes=attrs,
        files=[item(p,'native_terrain') for p in native.iterdir() if p.is_file()],hdf=rel(hdf))
    save(folder/'receipt.json',rec);return rec
