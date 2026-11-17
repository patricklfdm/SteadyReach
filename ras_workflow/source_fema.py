"""Coordinate-based FEMA source discovery using observed public catalog schemas."""
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.error import URLError
from pypdf.errors import PdfReadError
from .common import save, item, utc

NFHL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer'
MSC = 'https://msc.fema.gov/portal/'


def effective_reports(html):
    """Decode the public page's data literal as JSON, without executing scripts."""
    matches = list(re.finditer(r'(?m)^\s*var\s+data\s*=\s*(\{)', html))
    if len(matches) != 1:
        raise ValueError('FEMA product page schema changed. Open its product listing.')
    data, _ = json.JSONDecoder().raw_decode(html[matches[0].start(1):])
    reports = data.get('FIS_REPORT')
    if not isinstance(reports, list):
        raise ValueError('FEMA page did not provide a FIS report list')
    result = {}
    for record in reports:
        if not isinstance(record, dict):
            raise ValueError('FEMA report record schema changed')
        if (record.get('product_SUPERSEDED') != 'F' or str(record.get('product_EFFECTIVE_FLAG')) != '0'
            or record.get('product_TYPE_ID') != 'FINAL_PRODUCT'
            or record.get('product_SUBTYPE_ID') != 'FIS_REPORT'):
            continue
        product = record.get('product_NAME', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', product):
            raise ValueError('Unexpected FEMA product identifier')
        date = datetime.strptime(record['product_EFFECTIVE_DATE_STRING'], '%m/%d/%Y').date()
        if date > datetime.now(timezone.utc).date():
            continue
        url = MSC+'downloadProduct?'+urlencode(dict(productTypeID='FINAL_PRODUCT', productSubTypeID='FIS_REPORT', productID=product))
        result[product] = dict(product_id=product, effective_date=date.isoformat(), url=url,
                               community=record.get('ref_COMMUN_NAME'), catalog_record=record)
    return list(result.values())


def discover(model, location, output, download):
    from .app_acquisition import add_file, progress
    attempts, links, receipts = [], [], []
    def fetch(url, filename, limit=2_000_000):
        for attempt in range(2):
            try:
                raw = download.get(url, limit)
                break
            except (URLError, TimeoutError, ConnectionError):
                if attempt:
                    raise
        path = output/filename
        path.write_bytes(raw)
        receipt = dict(url=url, retrieved_utc=utc(), response=item(path), attempts=attempt+1)
        save(path.with_suffix(path.suffix+'.receipt.json'), receipt)
        receipts.extend([receipt['response'], item(path.with_suffix(path.suffix+'.receipt.json'))])
        return raw
    progress(model, 'Finding FEMA community and effective FIS reports / 查询 FEMA 社区与有效 FIS 报告')
    try:
        service = json.loads(fetch(NFHL+'?f=json', 'fema_service.json'))
        layers = [layer for layer in service.get('layers', []) if layer.get('name') == 'Political Jurisdictions']
        if len(layers) != 1:
            raise ValueError('FEMA jurisdiction layer unavailable')
        layer_url = NFHL+'/'+str(int(layers[0]['id']))
        schema = json.loads(fetch(layer_url+'?f=json', 'fema_jurisdiction_schema.json'))
        if not {'CID', 'POL_NAME1'} <= {field['name'] for field in schema.get('fields', [])}:
            raise ValueError('FEMA jurisdiction fields changed')
        query = layer_url+'/query?'+urlencode(dict(f='json', geometry=f"{location['longitude']},{location['latitude']}",
            geometryType='esriGeometryPoint', inSR=4326, spatialRel='esriSpatialRelIntersects',
            outFields='CID,POL_NAME1', returnGeometry='false', resultRecordCount=10))
        response = json.loads(fetch(query, 'fema_jurisdictions.json'))
        if response.get('error') or response.get('exceededTransferLimit'):
            raise ValueError('FEMA jurisdiction query is incomplete')
        communities = {feature['attributes']['CID']:feature['attributes']['POL_NAME1']
                       for feature in response.get('features', [])
                       if re.fullmatch(r'\d{6}', str(feature.get('attributes', {}).get('CID', '')))}
        if len(communities) > 4:
            raise ValueError('Multiple overlapping communities require location review')
        attempts.append(dict(route='FEMA_community_lookup', status='FOUND_RECORDS' if communities else 'NO_CATALOG_MATCH',
                             url=query, communities=communities, sources=list(receipts)))
    except (ValueError, KeyError, TypeError, OSError) as error:
        status = 'NETWORK_FAILED' if isinstance(error, OSError) else 'SOURCE_LOOKUP_FAILED'
        attempts.append(dict(route='FEMA_community_lookup', status=status, error=str(error), url=NFHL, sources=receipts))
        return attempts, links
    products = {}
    for community, name in communities.items():
        url = MSC+'availabilitySearch?'+urlencode(dict(addcommunity=community, communityName=name))
        links.append(dict(title=name+' — FEMA products and revisions', url=url))
        try:
            html = fetch(url, 'fema_products_'+community+'.html').decode('utf-8')
            reports = effective_reports(html)
            for report in reports:
                products[report['product_id']] = report
            attempts.append(dict(route='FEMA_effective_FIS_catalog', status='FOUND_RECORDS' if reports else 'NO_CATALOG_MATCH', url=url, sources=list(receipts)))
        except (ValueError, KeyError, TypeError, OSError) as error:
            status = 'NETWORK_FAILED' if isinstance(error, OSError) else 'SOURCE_LOOKUP_FAILED'
            attempts.append(dict(route='FEMA_effective_FIS_catalog', status=status, error=str(error), url=url, sources=list(receipts)))
    for index, report in enumerate(products.values()):
        links.append(dict(title=report['product_id']+' — effective '+report['effective_date'], url=report['url']))
        if index >= 6:
            attempts.append(dict(route='FEMA_FIS_download', status='DOWNLOAD_LIMIT_REACHED', url=report['url']))
            continue
        try:
            progress(model, 'Downloading FEMA '+report['product_id']+' / 下载有效 FIS 报告')
            raw = fetch(report['url'], report['product_id']+'.pdf', 15_000_000)
            if not raw.lstrip().startswith(b'%PDF-'):
                raise ValueError('FEMA returned a webpage or unsupported file instead of PDF')
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError('FEMA PDF is encrypted or contains no pages')
            source = add_file(model, report['product_id']+'.pdf', raw, report['url'])
            source['public_catalog'] = dict(provider='FEMA', product_id=report['product_id'],
                effective_date=report['effective_date'], community=report['community'], retrieved_utc=utc())
            attempts.append(dict(route='FEMA_FIS_download', status='DOWNLOADED', source=source, url=report['url'],
                                 pages=len(reader.pages), sources=list(receipts),
                                 note='Confirm the river segment and any applicable LOMRs. Effective publication date does not establish survey or hydrology date.'))
        except (ValueError, KeyError, TypeError, OSError, PdfReadError) as error:
            attempts.append(dict(route='FEMA_FIS_download', status='DOWNLOAD_FAILED', error=str(error), url=report['url'], sources=list(receipts)))
    return attempts, links
