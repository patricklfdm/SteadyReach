"""Crop/reproject map terrain within one horizontal datum; preserve raw elevations."""
import math
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from pyproj import CRS, Transformer
from .common import item, sha


def horizontal(value):
    crs=CRS.from_user_input(value)
    return crs.sub_crs_list[0] if crs.is_compound else crs.to_2d()


def terrain(raster,output,crs,bounds,factor,datum,vertical_unit):
    """Automatic projection conversion is allowed only within the same datum.

    No vertical CRS is passed to the warper. Vertical numbers change only by
    the explicitly reviewed unit factor. Datum changes need a separate review.
    """
    target=horizontal(crs)
    if not target.is_projected:raise ValueError('Map geometry CRS must be projected')
    if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
        raise ValueError('Invalid map extent')
    if not math.isfinite(factor) or factor<=0:raise ValueError('Invalid reviewed vertical unit conversion')
    with rasterio.open(raster) as src:
        if not src.crs or src.count!=1:raise ValueError('Terrain must have one elevation band and a CRS')
        source=horizontal(src.crs)
        if not source.is_projected:raise ValueError('Terrain source needs a projected CRS with known horizontal units')
        # GeoTIFF WKT1 may spell the same EPSG geodetic CRS as a reference
        # frame while the projection definition uses its WKT2 datum ensemble.
        if source.datum != target.datum and not source.geodetic_crs.equals(target.geodetic_crs, ignore_axis_order=True):
            raise ValueError('Terrain and model use different horizontal datums; provide an explicitly reviewed datum transformation')
        resolution=max(src.res)*source.axis_info[0].unit_conversion_factor/target.axis_info[0].unit_conversion_factor
        width=math.ceil((bounds[2]-bounds[0])/resolution);height=math.ceil((bounds[3]-bounds[1])/resolution)
        if width*height>25_000_000:raise ValueError('Map crop exceeds 25 million cells; review the extent/resolution')
        transform=from_bounds(*bounds,width,height)
        transformer=Transformer.from_crs(source,target,always_xy=True,allow_ballpark=False)
        # Explicit src_crs strips compound vertical information; the warper
        # cannot accidentally apply a geoid correction to elevation samples.
        with WarpedVRT(src,src_crs=source.to_wkt(),crs=target.to_wkt(),transform=transform,width=width,height=height,
                       resampling=Resampling.bilinear,nodata=-9999,dtype='float32') as warped:
            data=warped.read(1,masked=True)
        good=~np.ma.getmaskarray(data)&np.isfinite(data.data)
        if good.mean()<.98:raise ValueError(f'Terrain covers only {good.mean():.2%} of the map; extend terrain or review extent')
        values=np.where(good,data.data.astype('float64')*factor,-9999).astype('float32')
        with rasterio.open(output,'w',driver='GTiff',crs=target.to_wkt(),count=1,width=width,height=height,transform=transform,
                           dtype='float32',nodata=-9999,compress='deflate') as dst:
            dst.write(values,1);dst.update_tags(VERTICAL_DATUM=datum,VERTICAL_UNIT=vertical_unit,SOURCE_SHA256=sha(raster))
        return dict(source=item(raster),source_crs=source.to_wkt(),target_crs=target.to_wkt(),
            horizontal_reprojection=not source.equals(target,ignore_axis_order=True),
            horizontal_operation=transformer.description,horizontal_accuracy_m=transformer.accuracy,
            source_resolution=list(src.res),output_resolution=list(transform)[:1]+[abs(transform.e)],
            resampling='bilinear',unit_factor=factor,vertical_datum_changed=False,
            horizontal_datum_changed=False,valid_fraction=float(good.mean()),output=item(output))
