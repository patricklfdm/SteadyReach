"""FGDC metadata candidates with exact locators; never automatic datum approval."""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import rasterio
from pyproj import CRS

from .common import ROOT, intact, item, read, rel, safe_path, save, utc


def parse_fgdc(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML declarations/entities are not supported')
    root = ET.fromstring(data)
    for e in root.iter():
        e.tag = e.tag.rsplit('}', 1)[-1]
    if root.tag != 'metadata':
        raise ValueError('Unsupported metadata schema; FGDC metadata required')
    fields = {}
    def field(name, xpath):
        values = [{'value': ' '.join(''.join(e.itertext()).split()), 'locator': xpath + f'[{i+1}]'}
                  for i, e in enumerate(root.findall(xpath)) if ''.join(e.itertext()).strip()]
        unique = sorted({v['value'] for v in values})
        fields[name] = dict(value=unique[0] if len(unique)==1 else None, evidence=values,
                            status='CANDIDATE' if len(unique)==1 else ('MISSING' if not unique else 'CONFLICT'))
    for name, xpath in {
        'title':'./idinfo/citation/citeinfo/title', 'publication_date':'./idinfo/citation/citeinfo/pubdate',
        'temporal_start':'./idinfo/timeperd/timeinfo/rngdates/begdate',
        'temporal_end':'./idinfo/timeperd/timeinfo/rngdates/enddate',
        'time_meaning':'./idinfo/timeperd/current',
        'vertical_datum':'./spref/vertdef/altsys/altdatum',
        'vertical_unit':'./spref/vertdef/altsys/altunits',
        'horizontal_crs_description':'./spref/horizsys/planar/mapproj/mapprojn',
        'vertical_resolution_declared':'./spref/vertdef/altsys/altres',
        'vertical_accuracy_report':'./dataqual/posacc/vertacc/vertaccr',
    }.items():
        field(name, xpath)
    # Standard 1 m product XML sometimes omits spref but states elevations explicitly
    # in the abstract. Capture that exact claim separately from structured fields.
    for node in root.findall('./idinfo/descript/abstract'):
        text=' '.join(''.join(node.itertext()).split())
        claim=re.search(r'All bare earth elevation values are in meters and are referenced to the North American Vertical Datum of 1988 \(NAVD88\)',text)
        if claim:
            for name,value in [('vertical_unit','meters'),('vertical_datum','North American Vertical Datum of 1988')]:
                f=fields[name]
                f.setdefault('narrative_evidence',[]).append(dict(value=value,locator='./idinfo/descript/abstract',quote=claim.group(0)))
                if f['status']=='MISSING':
                    f.update(value=value,status='PROSE_CANDIDATE',method='Explicit metadata prose; applicability requires review')
    # Geoid is often documented only in project prose. Retain its actual text/locator.
    geoid = []
    for i, e in enumerate(root.iter()):
        if e.text:
            for m in re.finditer(r'\bGEOID\s*[- ]?\d{2,4}[A-Z]?\b', e.text, re.I):
                geoid.append(dict(value=m.group(0), locator=f'element[{i}]/{e.tag}', quote=e.text.strip()))
    unique = sorted({re.sub(r'\s|-', '', x['value']).upper() for x in geoid})
    fields['geoid'] = dict(value=unique[0] if len(unique)==1 else None, evidence=geoid,
                           status='CANDIDATE' if len(unique)==1 else ('MISSING' if not unique else 'CONFLICT'))
    units = {'meters':'m', 'meter':'m', 'metres':'m', 'metre':'m', 'US survey foot':'US survey foot',
             'U.S. survey feet':'US survey foot', 'international foot':'international foot'}
    fields['vertical_unit']['normalized'] = units.get(fields['vertical_unit']['value'])
    datums = {'North American Vertical Datum 1988':'NAVD88', 'North American Vertical Datum of 1988':'NAVD88', 'NAVD88':'NAVD88'}
    fields['vertical_datum']['normalized'] = datums.get(fields['vertical_datum']['value'])
    meaning = (fields['time_meaning']['value'] or '').lower()
    acquisition = 'ground condition' in meaning or 'acquisition' in meaning
    return dict(fields=fields, acquisition_start=fields['temporal_start']['value'] if acquisition else None,
                acquisition_end=fields['temporal_end']['value'] if acquisition else None,
                acquisition_date_status='CANDIDATE_REQUIRES_REVIEW' if acquisition else 'TIME_MEANING_UNRESOLVED')


def inspect(raster_path, xml_path, output):
    raster = safe_path(ROOT, raster_path); xml = safe_path(ROOT, xml_path)
    parsed = parse_fgdc(xml.read_bytes()); issues = []
    with rasterio.open(raster) as d:
        if d.crs is None:
            raise ValueError('Raster CRS is missing')
        crs = CRS.from_wkt(d.crs.to_wkt())
        horizontal = crs.sub_crs_list[0] if crs.is_compound else crs
        fields = parsed['fields']
        unit = fields['vertical_unit']['normalized']; datum = fields['vertical_datum']['normalized']
        if unit is None:issues.append('Explicit unambiguous vertical unit missing or unsupported')
        if datum is None:issues.append('Explicit recognized vertical datum missing or unsupported')
        if fields['geoid']['value'] is None:issues.append('Geoid missing/conflicting in this product XML; do not inherit a different project geoid')
        if parsed['acquisition_date_status']=='TIME_MEANING_UNRESOLVED':issues.append('Temporal extent is not explicitly an acquisition/ground-condition date')
        descriptions = fields['horizontal_crs_description']['value']
        horizontal_match = None
        if descriptions:
            try:horizontal_match = horizontal.equals(CRS.from_user_input(descriptions))
            except Exception:pass
        if horizontal_match is not True:issues.append('XML horizontal description requires CRS comparison review')
        if crs.is_compound:
            vc = crs.sub_crs_list[-1]
            expected = {'m':1.,'US survey foot':1200/3937,'international foot':.3048}.get(unit)
            if expected is not None and abs(vc.axis_info[0].unit_conversion_factor-expected)>1e-10:
                issues.append('CONFLICT: raster vertical CRS unit differs from XML')
            if datum=='NAVD88' and '1988' not in vc.datum.name and 'NAVD88' not in vc.name:
                issues.append('CONFLICT: raster vertical datum differs from XML')
        # File identity is still a candidate association; no hidden reprojection or relabeling.
        association = xml.stem == raster.stem or raster.name in xml.read_text(encoding='utf-8-sig')
        if not association:issues.append('Product XML/raster association is not established by name or download reference')
        raw = dict(crs_wkt=crs.to_wkt(),horizontal_crs=horizontal.to_string(),
                   horizontal_unit=horizontal.axis_info[0].unit_name,resolution=list(d.res),bounds=list(d.bounds),
                   nodata=str(d.nodata),width=d.width,height=d.height,tags=d.tags())
    result = dict(status='CANDIDATE_METADATA_REQUIRES_REVIEW',created_utc=utc(),
        sources=[item(raster,'actual_raster'),item(xml,'original_product_xml')],**parsed,
        actual_raster=raw,horizontal_crs_match=horizontal_match,product_association_candidate=association,
        review_items=issues,review_status='UNREVIEWED',
        limitations=['No coordinate/elevation transformation performed','Resolution is not a vertical accuracy statement',
                     'External terrain does not establish buried culvert dimensions or invert elevations'])
    out = safe_path(ROOT, output)
    if out.exists():raise ValueError('Choose a new metadata output; preserve prior evidence')
    save(out,result);return result


class Links(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            if href:self.urls.append(href)


def fetch_products(terrain_path, output):
    """Use links actually present in the saved catalog metadata page, not guessed URLs."""
    from .terrain import fetch
    terrain_path=safe_path(ROOT,terrain_path);terrain=read(terrain_path)
    folder=safe_path(ROOT,output);folder.mkdir(parents=True,exist_ok=False);records=[]
    for i,product in enumerate(terrain.get('products',[])):
        record=dict(product_id=product['product_id'],status='FAILED');records.append(record)
        try:
            if not intact([product['source'],product['metadata']]):raise ValueError('Product or metadata page hash changed')
            source=ROOT/product['source']['path'];page=ROOT/product['metadata']['path']
            links=Links();links.feed(page.read_text(encoding='utf-8-sig'))
            urls=sorted({u for u in links.urls if urllib.parse.unquote(urllib.parse.urlparse(u).path).split('/')[-1]==source.stem+'.xml'})
            if len(urls)!=1:raise ValueError('Product XML link absent or ambiguous in source metadata page')
            dest=folder/str(i)/ (source.stem+'.xml');fetch(urls[0],dest,10_000_000)
            candidate=dest.parent/'metadata.json';inspect(source,dest,candidate)
            record.update(status='CANDIDATE_REQUIRES_REVIEW',url=urls[0],result=item(candidate),link_source=item(page))
        except Exception as e:record['error']=str(e)
        save(folder/'manifest.json',dict(source=item(terrain_path),products=records,review_status='UNREVIEWED'))
    if not records:raise ValueError('No downloaded product entries; use terrain-metadata for explicit local XML')
    return records


def review_candidate(records):
    """Combine only intact, consistently identified products for wizard display."""
    entries=[];issues=[];paths=[]
    for record in records:
        if record.get('status')!='CANDIDATE_REQUIRES_REVIEW' or not record.get('result') or not intact([record['result']]):
            issues.append(record.get('error','Product metadata unavailable or changed'));continue
        data=read(ROOT/record['result']['path'])
        if not intact(data['sources']):issues.append('Metadata source changed');continue
        fields=data['fields'];entries.append(dict(product_id=record['product_id'],
            title=fields['title']['value'],unit=fields['vertical_unit']['normalized'],datum=fields['vertical_datum']['normalized'],
            evidence={k:fields[k] for k in ['vertical_unit','vertical_datum']},
            acquisition_start=data['acquisition_start'],acquisition_end=data['acquisition_end'],review_items=data['review_items']))
        paths.extend(e['path'] for e in data['sources'] if e['role']=='original_product_xml')
        issues.extend(data['review_items'])
        if not data.get('product_association_candidate'):issues.append('Product XML/raster association unresolved')
    units={e['unit'] for e in entries};datums={e['datum'] for e in entries}
    conflicts=any('CONFLICT' in issue or 'unresolved' in issue.lower() for issue in issues)
    consistent=bool(entries) and len(entries)==len(records) and len(units)==len(datums)==1 and None not in units|datums and not conflicts
    return dict(status='CANDIDATE_REQUIRES_REVIEW' if consistent else 'MANUAL_METADATA_REVIEW_REQUIRED',
        unit=next(iter(units)) if consistent else None,datum=next(iter(datums)) if consistent else None,
        source_paths=list(dict.fromkeys(paths)),products=entries,review_items=list(dict.fromkeys(issues)),reviewed=False)
