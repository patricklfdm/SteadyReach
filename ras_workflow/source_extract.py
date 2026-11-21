"""Conservative local document extraction. Text is evidence, never instructions."""
import csv
import io
import json
import math
import re
import subprocess
import sys
import zipfile
from importlib.metadata import PackageNotFoundError, version
import xml.etree.ElementTree as ET

EXTRACTOR_VERSION = 5
PDF_PAGE_LIMIT = 200
PDF_OCR_PAGE_LIMIT = 40
PDF_TEXT_LIMIT = 600_000
from pathlib import Path
from .common import ROOT, finite

def runtime_signature():
    packages = {}
    for name in ('pypdf', 'pypdfium2', 'winrt-runtime', 'winrt-Windows.Media.Ocr'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return dict(python=sys.executable, version=sys.version, packages=packages)


def reuse_document(cached, reuse_failed, runtime):
    if not cached or cached.get('extractor_version') != EXTRACTOR_VERSION:
        return False
    partial_ocr = any(isinstance(warning,str) and 'ocr failed' in warning.lower() for warning in cached.get('warnings', []))
    if cached.get('status') == 'INSPECTED' and not partial_ocr:
        return True
    return reuse_failed and cached.get('extraction_runtime') == runtime


def numeric(value):
    try:
        n=float(str(value).replace(',','').strip())
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def distance_m(lat,lon,a,b):
    from pyproj import Geod
    return abs(Geod(ellps='WGS84').inv(lon,lat,b,a)[2])

def csv_rows(path):
    text=Path(path).read_text(encoding='utf-8-sig')
    if len(text)>8_000_000: raise ValueError('CSV exceeds text extraction limit')
    try: dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
    if len(rows)>20_000: raise ValueError('CSV exceeds 20,000 rows')
    return [{str(k).strip():v for k,v in r.items() if k is not None} for r in rows]

def site_rows(rows,location):
    if not location:return []
    matches=[]
    for index,r in enumerate(rows):
        a=numeric(r.get('LAT'));b=numeric(r.get('LONG'))
        if a is None or b is None:continue
        distance=distance_m(location['latitude'],location['longitude'],a,b)
        if distance<=150:matches.append(dict(row=r,row_number=index+2,distance_m=round(distance,2)))
    return sorted(matches,key=lambda r:r['distance_m'])

def survey(rows,mapping=None):
    if not rows:return None
    names={re.sub(r'[^a-z0-9]','',k.lower()):k for k in rows[0]}
    aliases={'id':['surve ypt'.replace(' ',''),'point','pointid','pointnumber','pt'],
        'x':['easting','east','x'],'y':['northing','north','y'],
        'z':['elevfeet','elevationft','elevation','elev','z'],
        'code':['location','description','desc','code']}
    columns={k:next((names[a] for a in aa if a in names),None) for k,aa in aliases.items()}
    columns.update({k:v for k,v in (mapping or {}).items() if k in aliases and v})
    if not all(columns.get(k) in rows[0] for k in ('x','y','z')):
        return dict(columns=columns,headers=list(rows[0]),points=[],status='COLUMN_MAPPING_REQUIRED')
    points=[];invalid=[]
    for i,r in enumerate(rows):
        xyz=[numeric(r.get(columns[k])) for k in ('x','y','z')]
        if any(v is None for v in xyz):invalid.append(i+2);continue
        points.append(dict(id=str(r.get(columns.get('id'),i+1)),x=xyz[0],y=xyz[1],z=xyz[2],code=str(r.get(columns.get('code'),'')),row=i+2))
    return dict(columns=columns,headers=list(rows[0]),points=points,invalid_rows=invalid,status='PARSED' if points else 'NO_VALID_POINTS')

def document_text(path, scratch, ocr=True):
    path = Path(path)
    suffix = path.suffix.lower()
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    if suffix in ('.txt', '.xml', '.kml'):
        raw = path.read_text(encoding='utf-8-sig')[:300_000]
        if suffix == '.kml':
            return kml_text(raw)
        return dict(text=raw, method='text', warnings=[])
    if suffix in ('.docx', '.kmz'):
        with zipfile.ZipFile(path) as archive:
            names = ['word/document.xml'] if suffix == '.docx' else [n for n in archive.namelist() if n.lower().endswith('.kml')]
            if sum(archive.getinfo(n).file_size for n in names) > 8_000_000:
                raise ValueError('Document XML exceeds the 8 MB extraction bound')
            if suffix == '.kmz':
                documents = [kml_text(archive.read(n)) for n in names]
                return dict(text='\n'.join(d['text'] for d in documents), method='KML placemarks',
                            locations=[p for d in documents for p in d['locations']], warnings=[])
            root = ET.fromstring(archive.read(names[0]))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = [''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in root.findall('.//w:p', ns)]
            return dict(text='\n'.join(paragraphs)[:300_000], method='DOCX paragraphs and tables',
                        warnings=['Embedded drawing/image labels need visual inspection or image OCR'])
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        warnings = []
        methods = []
        tables = []
        pdf = None
        ocr_pages = 0
        characters = 0
        incomplete = False
        try:
            for i, page in enumerate(reader.pages[:PDF_PAGE_LIMIT]):
                try:
                    raw = page.extract_text() or ''
                except Exception as error:
                    raw = ''
                    warnings.append(f'Page {i+1} text extraction failed: {error}')
                method = 'PDF text'
                if re.search(r'Summary of Discharges|Roughness Coefficients', ' '.join(raw.split()), re.I):
                    try:
                        from .source_tables import parse
                        parsed = parse(page.extract_text(extraction_mode='layout') or '', i+1)
                        tables.extend(parsed)
                        for table in parsed:
                            warnings.extend(f'Page {i+1} table extraction: '+warning for warning in table['warnings'])
                    except Exception as error:
                        warnings.append(f'Page {i+1} table extraction failed: {error}')
                if len(raw.strip()) < 80 and ocr and ocr_pages < PDF_OCR_PAGE_LIMIT:
                    ocr_pages += 1
                    try:
                        import pypdfium2 as pdfium
                        if pdf is None:
                            pdf = pdfium.PdfDocument(path)
                        rendered = pdf[i]
                        bitmap = rendered.render(scale=1.8)
                        image = bitmap.to_pil()
                        try:
                            target = scratch / f'page_{i+1}.png'
                            image.save(target)
                            recognized = image_text(target, scratch)
                            if len(recognized.strip()) > len(raw.strip()):
                                raw = recognized
                                method = 'Windows OCR unverified'
                        finally:
                            image.close()
                            bitmap.close()
                            rendered.close()
                    except Exception as error:
                        warnings.append(f'Page {i+1} OCR failed: {error}')
                if len(raw.strip()) < 80:
                    incomplete = True
                    warnings.append(f'Page {i+1} has little extractable text; inspect the original page')
                text = f'[Page {i+1}; {method}]\n{raw}'
                remaining = PDF_TEXT_LIMIT - characters
                parts.append(text[:remaining])
                characters += len(parts[-1]) + 1
                methods.append(method)
                if len(text) > remaining or characters >= PDF_TEXT_LIMIT:
                    incomplete = True
                    warnings.append(f'PDF text reached the {PDF_TEXT_LIMIT:,}-character extraction limit')
                    break
        finally:
            if pdf is not None:
                pdf.close()
        if len(methods) < len(reader.pages):
            incomplete = True
            warnings.append(f'Inspected {len(methods)} of {len(reader.pages)} PDF pages; remaining pages require review')
        if ocr_pages >= PDF_OCR_PAGE_LIMIT:
            warnings.append(f'Automatic OCR is limited to {PDF_OCR_PAGE_LIMIT} pages per PDF')
        return dict(text='\n'.join(parts), method='PDF text + OCR' if any('OCR' in m for m in methods) else 'PDF text',
                    page_methods=methods, tables=tables, warnings=warnings,
                    coverage=dict(total_pages=len(reader.pages), inspected_pages=len(methods), ocr_pages=ocr_pages,
                                  status='PARTIAL' if incomplete else 'COMPLETE_TEXT_PASS'))
    if suffix in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'):
        from .local_ocr import NoReadableText
        try:
            text=image_text(path,scratch) if ocr else ''
        except NoReadableText:
            return dict(text='',method='Windows OCR',visual_only=True,
                        warnings=['No readable text. Inspect the original image for visible site features.'])
        return dict(text=text, method='Windows OCR',
                    warnings=['Photo / handwriting recognition is unverified; feature identity requires review'])
    return dict(text='', method='unsupported', warnings=['No extractor for this file type; original retained'])


def kml_text(raw):
    root = ET.fromstring(raw)
    ns = {'k': 'http://www.opengis.net/kml/2.2'}
    locations = []
    for placemark in root.findall('.//k:Placemark', ns):
        coords = placemark.findtext('k:Point/k:coordinates', default='', namespaces=ns).strip().split(',')
        if len(coords) < 2:
            continue
        lon, lat = numeric(coords[0]), numeric(coords[1])
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        locations.append(dict(name=placemark.findtext('k:name', default='', namespaces=ns), latitude=lat, longitude=lon))
    return dict(text='\n'.join(f"Placemark {p['name']}: latitude {p['latitude']}, longitude {p['longitude']}" for p in locations),
                locations=locations, method='KML placemarks', warnings=[])


def image_text(path,scratch):
    from .local_ocr import image_text as recognize
    return recognize(path,scratch)


def control_context(documents,points):
    """Infer this documented SPC convention only with two independent controls.

    Merely seeing the word NAVD88 is insufficient: match the explicit orthometric
    height and both metric grid ordinates to the survey's named RM control rows.
    """
    controls=[]
    for d in documents:
        text=d.get('text','');name=Path(d['source']['path']).name
        rm=re.search(r'\b(RM\d+)(?=_|\b)',name,re.I)
        if not rm or not all(s in text for s in ('NAVD88','NAD_83(2011)','MA M')):continue
        n=re.search(r'Northing\s*\(Y\)\s*\[meters\]\s*:?\s*[\d.]+\s+([\d.]+)',text,re.I)
        e=re.search(r'Easting\s*\(X\)\s*\[meters\]\s*:?\s*[\d.]+\s+([\d.]+)',text,re.I)
        h=re.search(r'ORTHO\s+HGT\s*:\s*([-\d.]+)',text,re.I)
        point=next((p for p in points if p['id'].upper()==rm[1].upper()),None) or next((p for p in points if p['code'].upper()==rm[1].upper()),None)
        if not (n and e and h and point):continue
        factor=1200/3937
        errors=[abs(point['x']*factor-float(e[1])),abs(point['y']*factor-float(n[1])),abs(point['z']*factor-float(h[1]))]
        if max(errors)<.03:controls.append(dict(control=rm[1],max_residual_m=max(errors),source=d['source']))
    if len({c['control'].upper() for c in controls})<2:return None
    return dict(horizontal_crs='EPSG:6492',vertical_unit='US survey foot',vertical_datum='NAVD88',controls=controls,
        basis='Two OPUS controls explicitly identify NAD83(2011), MA Mainland and NAVD88; metric coordinates/heights agree with survey-foot CSV within 0.03 m. Verify site/epoch applicability.')

def parameter_rows(rows,allowed):
    """Explicit field/value CSV only; arbitrary prose is never assigned silently."""
    result=[];errors=[]
    for i,r in enumerate(rows):
        if not {'field','value'}<=set(r):return [],[]
        key=r['field'].strip();f=allowed.get(key)
        try:
            if f is None:raise ValueError('Unknown parameter field')
            raw=r['value'].strip()
            if not raw:continue
            value=json.loads(raw) if f['kind'] in ('array','matrix') else numeric(raw) if f['kind'] in ('integer','number') else raw
            if value is None:raise ValueError('Invalid finite number')
            if f['kind']=='integer' and int(value)!=value:raise ValueError('Integer required')
            if f['kind']=='integer':value=int(value)
            if f['kind'] in ('array','matrix'):
                if not isinstance(value,list) or not value:raise ValueError('Nonempty numeric array required')
                if f['kind']=='array' and not all(finite(v) for v in value):raise ValueError('Array must contain finite numbers')
                if f['kind']=='matrix' and not all(isinstance(row,list) and row and all(finite(v) for v in row) for row in value):raise ValueError('Matrix must contain finite numeric rows')
            if f['kind']=='choice' and value not in f['options']:raise ValueError('Unsupported choice')
            required_unit=f.get('unit') or ''
            if required_unit and r.get('unit','').strip()!=required_unit:raise ValueError('Unit must explicitly match '+required_unit)
            classification=(r.get('evidence_class') or '').strip().lower() or 'reported'
            if classification not in ('reported','assumed'):
                raise ValueError('Use reported or assumed for evidence_class')
            result.append(dict(field=key,value=value,row=i+2,evidence_class=classification,datum=r.get('datum'),basis=r.get('source') or 'Explicit parameter CSV row'))
        except (ValueError,TypeError) as e:errors.append(dict(row=i+2,field=key,error=str(e)))
    return result,errors

def text_flows(text):
    """Small, auditable extractor; ambiguous document flows remain candidates."""
    found=[]
    for m in re.finditer(r'(?i)(?<![\d.])\b(?:Q\s*100|100[- ]year|1\s*(?:%|[- ]percent)\s*AEP)\b[^\n\d]{0,45}([\d,]+(?:\.\d+)?)\s*(cfs|ft(?:\^?3|³)/s|m(?:\^?3|³)/s)\b',text):
        value=numeric(m[1])
        if value and value>0:found.append(dict(value=round(value*(35.3146667 if m[2].lower().startswith('m') else 1),6),excerpt=m[0]))
    return found

def text_parameters(text,allowed):
    """Extract explicit labels with units; no assignment from unlabeled numbers."""
    aliases={'c.scenarios.0.channel_n':r'(?:channel|bottom|主槽|河床)\s*(?:Manning.?s?\s*)?(?:n|roughness|糙率)?',
        'c.scenarios.0.overbank_n':r'(?:overbank|bank|漫滩|河岸)\s*(?:Manning.?s?\s*)?(?:n|roughness|糙率)?',
        'g.structure.groups.0.length_ft':r'(?:culvert|barrel|涵洞)\s*(?:length|长度|涵长)',
        'g.structure.road.width_ft':r'(?:road|roadway|路面)\s*(?:crossing\s+)?(?:width|宽度)'}
    out=[]
    for key,label in aliases.items():
        if key not in allowed:continue
        if key=='g.structure.groups.0.length_ft' and 'g.structure.groups.1.length_ft' in allowed:continue
        length=key.endswith('_ft')
        pattern=label+r'\s*[:=]?\s*(\d+(?:\.\d+)?|\.\d+)'+(r'\s*(ft|feet|m|meters)\b' if length else r'(?![\d.])')
        for match in re.finditer(pattern,text,re.I):
            value=numeric(match[1])
            if value is None or value<=0 or not length and value>=1:continue
            if length and match[2].lower() in ('m','meters'):value/=.3048
            out.append(dict(field=key,value=round(value,6),excerpt=match[0]))
    # Explicit group labels only; dimensions without a group must not populate
    # the first opening of a multiple-group crossing.
    aliases={'length_ft':r'(?:barrel\s+)?length','span_ft':r'(?:clear\s+)?(?:width|diameter|span)',
             'rise_ft':r'(?:clear\s+)?(?:height|rise)'}
    for name,label in aliases.items():
        pattern=r'\b(?:group|culvert\s+group)\s+(\d+)\s*[:;,\-]?\s*'+label+r'\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ft|feet|m|meters)\b'
        for match in re.finditer(pattern,text,re.I):
            key=f'g.structure.groups.{int(match[1])-1}.'+name
            if key not in allowed:continue
            value=float(match[2])*(1/.3048 if match[3].lower() in ('m','meters') else 1)
            if value>0:out.append(dict(field=key,value=round(value,6),excerpt=match[0]))
    return out + opening_parameters(text, allowed) + group_blocks(text, allowed)


def group_blocks(text, allowed):
    """Read numbered group blocks with explicit labels, dimensions and datum."""
    headings=list(re.finditer(r'(?im)^\s*(?:culvert\s+group|group|涵孔组)\s*(\d+)\s*[:：\-]?[^\n]*',text))
    result=[]
    labels={'length_ft':r'(?:barrel\s+|culvert\s+)?length|涵长',
            'span_ft':r'(?:clear\s+)?(?:width|span|diameter)|净宽|直径',
            'rise_ft':r'(?:clear\s+)?(?:height|rise)|净高',
            'us_invert_ft':r'(?:inlet|upstream|US)\s+invert|进口涵底',
            'ds_invert_ft':r'(?:outlet|downstream|DS)\s+invert|出口涵底'}
    for i,heading in enumerate(headings):
        prefix=f'g.structure.groups.{int(heading[1])-1}.'
        block=text[heading.start():headings[i+1].start() if i+1<len(headings) else len(text)][:6000]
        datums=set(re.findall(r'\b(?:NAVD88|NGVD29)\b',block,re.I))
        datum=next(iter(datums)).upper() if len(datums)==1 else None
        classification='assumed' if re.search(r'assum|hypothes|approx|nominal|estimate|假设|估[计算]',block,re.I) else 'reported'
        for name,label in labels.items():
            key=prefix+name
            if key not in allowed or 'invert' in name and datum is None:
                continue
            pattern=r'(?:'+label+r')\s*[:=：]?\s*(-?\d+(?:\.\d+)?)\s*(US\s+survey\s+(?:ft|feet)|ft|feet|meters?|m)\b'
            for match in re.finditer(pattern,block,re.I):
                unit=match[2].lower()
                factor=(1200/3937)/.3048 if unit.startswith('us') else 1/.3048 if unit.startswith('m') else 1.
                value=float(match[1])*factor
                if 'invert' not in name and value<=0:
                    continue
                row=dict(field=key,value=round(value,6),evidence_class=classification,
                         excerpt=heading[0].strip()+' / '+match[0])
                if 'invert' in name:
                    row['datum']=datum
                    row['excerpt']+=' / '+datum
                result.append(row)
    return result


def opening_parameters(text, allowed):
    """Explicit dimensions for a single group; preserve conditional wording."""
    if 'g.structure.groups.1.shape' in allowed:
        return []
    prefix = 'g.structure.groups.0.'
    result = []
    def add(name, value, match):
        key = prefix + name
        if key not in allowed:
            return
        # Keep the enclosing sentence and preceding label for attribution.
        excerpt = text[max(0, match.start()-100):min(len(text), match.end()+100)].strip()
        assumed = re.search(r'assum|hypothes|appears|approx|nominal|estimate|假设|估[计算]', excerpt, re.I)
        result.append(dict(field=key, value=value, excerpt=excerpt,
                           evidence_class='assumed' if assumed else 'reported'))
    for match in re.finditer(r'\b(\d+|one|two|three|four)\s*[- ](?:cell|barrel)\s+(?:concrete\s+)?box\s+culvert', text, re.I):
        token = match[1].lower()
        count = int(token) if token.isdigit() else {'one': 1, 'two': 2, 'three': 3, 'four': 4}[token]
        if 1 <= count <= 25:
            add('shape', 'box', match)
            add('count', count, match)
    for name, label in [('span_ft', 'width'), ('rise_ft', 'height')]:
        pattern = r'\b' + label + r'\s+per\s+(?:cell|barrel)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ft|feet|m|meters)\b'
        for match in re.finditer(pattern, text, re.I):
            value = float(match[1]) * (1/.3048 if match[2].lower() in ('m', 'meters') else 1)
            if value > 0:
                add(name, round(value, 6), match)
    for match in re.finditer(r'\b(\d+(?:\.\d+)?)\s*(ft|feet|m|meters)\s*[×x]\s*(\d+(?:\.\d+)?)\s*\2\s+(?:box\s+)?(?:barrels|cells)', text, re.I):
        factor = 1/.3048 if match[2].lower() in ('m', 'meters') else 1
        add('span_ft', round(float(match[1])*factor, 6), match)
        add('rise_ft', round(float(match[3])*factor, 6), match)
    return result
