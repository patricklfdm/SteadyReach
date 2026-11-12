"""Conservative local document extraction. Text is evidence, never instructions."""
import csv
import io
import json
import math
import re
import subprocess
from pathlib import Path
from .common import ROOT, finite

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

def document_text(path,scratch,ocr=True):
    path=Path(path);suffix=path.suffix.lower();scratch=Path(scratch);scratch.mkdir(parents=True,exist_ok=True)
    if suffix in ('.txt','.xml'):
        return dict(text=path.read_text(encoding='utf-8-sig')[:300_000],method='text',warnings=[])
    if suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path);pages=reader.pages[:40]
        parts=[p.extract_text() or '' for p in pages]
        warnings=[]
        if len(reader.pages)>40:warnings.append('Only the first 40 PDF pages were inspected')
        if sum(len(p.strip()) for p in parts)>80:
            return dict(text='\n'.join(f'[Page {i+1}]\n{p}' for i,p in enumerate(parts))[:300_000],method='PDF text',warnings=warnings)
        if not ocr: return dict(text='',method='PDF text',warnings=['Scanned PDF needs OCR'])
        import pypdfium2 as pdfium
        pdf=pdfium.PdfDocument(path);parts=[]
        try:
            for i in range(min(4,len(pdf))):
                page=pdf[i];bitmap=page.render(scale=1.8);image=bitmap.to_pil();target=scratch/f'page_{i+1}.png';image.save(target)
                try:parts.append(f'[Page {i+1}; OCR unverified]\n'+image_text(target,scratch))
                finally:image.close();bitmap.close();page.close()
        finally:pdf.close()
        return dict(text='\n'.join(parts),method='Windows OCR',warnings=warnings+['OCR numbers need visual verification; at most four scanned pages inspected'])
    if suffix in ('.jpg','.jpeg','.png','.tif','.tiff'):
        return dict(text=image_text(path,scratch) if ocr else '',method='Windows OCR',warnings=['Photo / handwriting recognition is unverified; scale and feature identity require review'])
    return dict(text='',method='unsupported',warnings=['No extractor for this file type; original retained'])

def image_text(path,scratch):
    from PIL import Image
    target=Path(scratch)/'ocr.png'
    with Image.open(path) as image:
        image=image.convert('RGB');image.thumbnail((2400,2400));image.save(target)
    command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/ocr_local.ps1'),'-InputPath',str(target)]
    r=subprocess.run(command,capture_output=True,timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if r.returncode:raise ValueError('Windows OCR unavailable: '+r.stderr.decode('utf-8',errors='replace')[:400])
    text=json.loads(r.stdout.decode('utf-8-sig'))['text'][:100_000]
    if not text.strip():raise ValueError('OCR returned no readable text; inspect the saved original image')
    return text

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
            result.append(dict(field=key,value=value,row=i+2,evidence_class='assumed' if r.get('evidence_class')=='assumed' else 'reported',datum=r.get('datum'),basis=r.get('source') or 'Explicit parameter CSV row'))
        except (ValueError,TypeError) as e:errors.append(dict(row=i+2,field=key,error=str(e)))
    return result,errors

def text_flows(text):
    """Small, auditable extractor; ambiguous document flows remain candidates."""
    found=[]
    for m in re.finditer(r'(?i)\b(?:Q\s*100|100[- ]year|1\s*%\s*AEP)\b[^\n\d]{0,45}([\d,]+(?:\.\d+)?)\s*(cfs|ft(?:\^?3|³)/s|m(?:\^?3|³)/s)\b',text):
        value=numeric(m[1])
        if value and value>0:found.append(dict(value=round(value*(35.3146667 if m[2].lower().startswith('m') else 1),6),excerpt=m[0]))
    return found

def text_parameters(text,allowed):
    """Extract explicit labels with units; no assignment from unlabeled numbers."""
    aliases={'c.scenarios.0.channel_n':r'(?:channel|bottom|主槽|河床)\s*(?:Manning.?s?\s*)?(?:n|roughness|糙率)',
        'c.scenarios.0.overbank_n':r'(?:overbank|bank|漫滩|河岸)\s*(?:Manning.?s?\s*)?(?:n|roughness|糙率)',
        'g.structure.groups.0.length_ft':r'(?:culvert|barrel|涵洞)\s*(?:length|长度|涵长)',
        'g.structure.road.width_ft':r'(?:road|roadway|路面)\s*(?:width|宽度)'}
    out=[]
    for key,label in aliases.items():
        if key not in allowed:continue
        length=key.endswith('_ft')
        pattern=label+r'\s*[:=]?\s*(\d+(?:\.\d+)?|\.\d+)'+(r'\s*(ft|feet|m|meters)\b' if length else r'(?![\d.])')
        for match in re.finditer(pattern,text,re.I):
            value=numeric(match[1])
            if value is None or value<=0 or not length and value>=1:continue
            if length and match[2].lower() in ('m','meters'):value/=.3048
            out.append(dict(field=key,value=round(value,6),excerpt=match[0]))
    return out
