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


def map_bounds(bounds, margin=.08):
    margin=float(margin)
    if not 0<=margin<=.5:
        raise ValueError('map_margin_fraction must be between 0 and 0.5')
    x0,y0,x1,y1=bounds
    if x1<=x0 or y1<=y0:
        raise ValueError('Degenerate geographic extent')
    cx,cy=(x0+x1)/2,(y0+y1)/2
    radius=max(x1-x0,y1-y0)*(.5+margin)
    return [cx-radius,cy-radius,cx+radius,cy+radius]


def terrain_crs(src,target):
    if not src.crs or src.count!=1:
        raise ValueError('Terrain must have one elevation band and a CRS')
    source=horizontal(src.crs)
    if not source.is_projected:
        raise ValueError('Terrain source needs a projected CRS with known horizontal units')
    # WKT1 and WKT2 can use different spellings of the same geodetic CRS.
    if source.datum!=target.datum and not source.geodetic_crs.equals(target.geodetic_crs,ignore_axis_order=True):
        raise ValueError('Terrain and model use different horizontal datums; provide an explicitly reviewed datum transformation')
    return source


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
        source=terrain_crs(src,target)
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
        if output is None:
            return dict(bounds=list(bounds),width=width,height=height,valid_fraction=float(good.mean()),
                        source_crs=source.to_string(),target_crs=target.to_string())
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
