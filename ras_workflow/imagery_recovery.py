"""Recover a display mosaic from a sealed package after a recorded NAIP pixel transfer failure."""
import json
from urllib.parse import parse_qs, urlsplit

import rasterio
from pyproj import CRS

from .common import ROOT, intact, item, read, safe_path, sha
from .imagery import SERVICE


def contains(outer, inner):
    return (len(outer)==len(inner)==4 and outer[0]<=inner[0]<inner[2]<=outer[2]
            and outer[1]<=inner[1]<inner[3]<=outer[3])


def parent_mosaic(configuration,crs,bounds):
    """A revision may retain its parent's dated map background over the identical extent."""
    origin=configuration.get('revision_origin') or {}
    entry=origin.get('summary')
    if not entry or not intact([entry]):
        return None
    from .site_delivery import latest,cached_imagery
    try:
        path=safe_path(ROOT,entry['path'])
        parent=read(path)['configuration']
        if parent.get('project_id')!=origin.get('project_id'):
            return None
        package=latest(path)
        if not package or not package.get('mapped') or package.get('summary')!=entry:
            return None
        acquired=cached_imagery(package['complete']['path'],crs,bounds,allow_new_extent=True)
        if acquired and acquired['acquisition'].get('service')==SERVICE:
            return dict(acquired,parent_summary=entry)
    except (KeyError,ValueError,OSError,TypeError):
        # An unusable prior mosaic leaves the normal catalogue search available.
        return None
    return None


def _live_selection(query, crs, bounds):
    if not (query/'acquisition.json').is_file():
        return None
    state=read(query/'acquisition.json')
    # Older receipts predate the explicit transfer flag. Recover their observed
    # Windows connection-reset case only, and still verify the catalogue below.
    transfer=state.get('pixel_transfer_failed')
    if transfer is None:
        transfer=str(state.get('error','')).startswith('<urlopen error [WinError 10054]')
    if (transfer is not True or state.get('status')!='FAILED' or state.get('service')!=SERVICE
            or state.get('requested_bounds')!=list(bounds) or not CRS.from_user_input(state['requested_crs']).equals(crs)):
        return None
    receipts=state.get('requests',[])
    for filename,route in [('catalog.json','/query'),('export.json','/exportImage')]:
        path=query/filename
        if not path.is_file() or not path.with_suffix('.json.request.json').is_file():
            return None
        receipt=read(path.with_suffix('.json.request.json'))
        if (receipt not in receipts or receipt.get('tls_verification') is not True
                or receipt.get('url','').partition('?')[0]!=SERVICE+route or sha(path)!=receipt['sha256']):
            return None
    params=parse_qs(urlsplit(receipt['url']).query)
    if json.loads(params['renderingRule'][0])!={'rasterFunction':'NaturalColor'} or [float(v) for v in params['bbox'][0].split(',')]!=list(bounds):
        return None
    rule=json.loads(params['mosaicRule'][0])
    catalog=read(query/'catalog.json')
    key=catalog['objectIdFieldName']
    current={r['attributes'][key]:r['attributes'] for r in catalog['features']}
    ids=rule['lockRasterIds']
    if not ids or any(i not in current for i in ids):
        return None
    return rule, [current[i] for i in ids]


def lookup(query, crs, bounds):
    try:
        selection = _live_selection(query, crs, bounds)
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        return None
    if selection is None:
        return None
    rule, records = selection
    # Check registered Complete deliveries only. Validate all package bytes before use.
    from .site_delivery import verify
    for index in sorted((ROOT/'status/delivery_catalogs').glob('*/catalog.json')):
        try:
            editions=read(index)['editions']
            for edition in reversed(editions):
                if not intact([edition]):
                    continue
                completed=read(safe_path(ROOT,edition['path']))
                if not completed.get('mapped') or completed.get('status')!='READY_FOR_REVIEW':
                    continue
                complete=completed['complete']
                package=safe_path(ROOT,complete['path'])
                source=package/'Evidence/imagery.json'
                r=read(source)
                r=r.get('acquisition',r)
                if (r.get('service')!=SERVICE or r.get('valid_fraction')!=1 or r.get('status')!='READY_FOR_MAP_REVIEW'
                        or r.get('mosaic_rule')!=rule or not contains(r['returned_bounds'],bounds)
                        or not CRS.from_user_input(r['requested_crs']).equals(crs)
                        or r['source_records']!=records):
                    continue
                manifest=complete['manifest']
                if safe_path(ROOT,manifest['path'])!=package/'PACKAGE_MANIFEST.json' or not intact([manifest]):
                    continue
                verify(package)
                raster=package/'GIS/Aerial.tif'
                if sha(raster)!=r['raster']['sha256']:
                    continue
                with rasterio.open(raster) as dataset:
                    if not contains(dataset.bounds,bounds) or dataset.count!=3 or not CRS.from_user_input(dataset.crs).equals(crs):
                        continue
                return dict(method='REUSED_VERIFIED_OFFLINE_MOSAIC',acquisition=r,source=r['source'],raster=item(raster),
                            requested_map_bounds=list(bounds),coverage='COMPLETE_CONTAINMENT_MATCHING_LIVE_CATALOG',
                            previous_receipt=item(source),previous_manifest=manifest,network_requests=0)
        except (ValueError,KeyError,TypeError,OSError):
            continue
    return None
