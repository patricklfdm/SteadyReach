"""Pinned public native baselines with CSV references separate from solver inputs."""
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path
from .common import ROOT, finite, intact, item, read, rel, safe_path, save, utc
from .benchmark import obtain, selected_members
from .qa_review import load_summary
from .qa import number


def recipe(path):
    path=safe_path(ROOT,path);r=read(path)
    if r.get('schema_version')!='public_csv_case_1.0':raise ValueError('Unsupported public CSV recipe')
    if not intact([r['project_template']]):raise ValueError('Public project template changed')
    return path,r


def csv_reference(archive,ref):
    with zipfile.ZipFile(archive) as z:
        if z.namelist().count(ref['member'])!=1:raise ValueError('Ambiguous published CSV member')
        e=z.getinfo(ref['member'])
        if e.file_size!=ref['size_bytes'] or e.file_size>5_000_000:raise ValueError('Published CSV size mismatch')
        raw=z.read(e)
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Published CSV hash mismatch')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    matching=[v for v in rows if all(v.get(k)==wanted for k,wanted in ref['row_selector'].items())]
    if len(matching)!=1:raise ValueError('Published row is missing or ambiguous')
    return raw,matching[0]


def prepare(recipe_path,output,fetch=False):
    rp,r=recipe(recipe_path);out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve existing public inputs; choose a new directory')
    archive=obtain(r['archive'],fetch);metadata=[obtain(e,fetch) for e in r.get('metadata',[])]
    native=selected_members(archive,r['members']);raw,row=csv_reference(archive,r['reference'])
    out.mkdir(parents=True);source=out/'source';source.mkdir();dest=out/'inputs';dest.mkdir()
    adaptations=[]
    for name,data in native.items():
        (source/name).write_bytes(data)
        normal=data.replace(b'\r\r\n',b'\r\n')
        if Path(name).suffix.lower()=='.prj':
            text=normal.decode('ascii');lines=text.splitlines()
            for line in ['Geom File=g01','Flow File=f01','Plan File=p01']:
                if lines.count(line)!=1:raise ValueError('Public baseline selector is missing or ambiguous: '+line)
            lines=[l for l in lines if not re.match(r'^(?:Geom|Flow|Plan) File=',l) or l.endswith('01')]
            normal=('\r\n'.join('Current Plan=p01' if l.startswith('Current Plan=') else l for l in lines)+'\r\n').encode('ascii')
        (dest/name).write_bytes(normal)
        adaptations.append(dict(source=item(source/name),prepared=item(dest/name),
            change='Normalize duplicate CRCRLF delimiters; restrict only .prj selector/lists to p01/g01/f01'))
    (source/'published.csv').write_bytes(raw)
    c=read(ROOT/r['project_template']['path']);c['benchmark_preparation']='preparation.json';save(out/'project.json',c)
    prep=dict(schema_version='public_csv_preparation_1.0',created_utc=utc(),recipe=item(rp),files=[item(p) for p in dest.iterdir()],
        source_snapshots=[item(p) for p in source.iterdir()]+[item(archive)]+[item(p) for p in metadata],adaptations=adaptations,
        reference_csv=item(source/'published.csv'),project=item(out/'project.json'),limitations=r['limitations'])
    save(out/'preparation.json',prep)
    return out/'project.json'


def compare(recipe_path,summary_path,output):
    rp,r=recipe(recipe_path);sp,s,hyd=load_summary(summary_path);out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve earlier comparisons; choose a new output')
    archive=obtain(r['archive']);_,ref=csv_reference(archive,r['reference'])
    c=read(ROOT/r['project_template']['path'])
    if s['configuration'].get('expected_native')!=c['expected_native']:raise ValueError('Native readback specification differs from pinned case')
    solver=(ROOT/hyd['raw_hdf']['path']).parent.parent;m=read(solver/'manifest.json')
    if not intact(m['native_before']+m['outputs']):raise ValueError('Native evidence changed')
    originals=selected_members(archive,r['members'])
    for name,raw in originals.items():
        if Path(name).suffix.lower()=='.prj':continue
        imported=bool(s['configuration'].get('native_import_review'))
        found=[e for e in m['native_before'] if (Path(e['path']).suffix.lower()==Path(name).suffix.lower() if imported else Path(e['path']).name.lower()==name.lower())]
        normalized=raw.replace(b'\r\r\n',b'\r\n')
        if len(found)!=1:raise ValueError('Hydraulic input missing or ambiguous: '+name)
        actual=(ROOT/found[0]['path']).read_bytes()
        if imported and Path(name).suffix.lower()=='.p01':
            # Importer may normalize line delimiters, never hydraulic plan cards.
            actual=actual.replace(b'\r\n',b'\n');normalized=normalized.replace(b'\r\n',b'\n')
        if actual!=normalized:raise ValueError('Hydraulic input differs from published baseline: '+name)
    if hyd.get('unit')!=r['reference']['native_unit']:raise ValueError('Published/native units differ')
    com=read(ROOT/hyd['raw_controller']['path']);rows=[]
    for mapping in r['reference']['metrics']:
        tolerance=mapping['tolerance']
        if not finite(tolerance) or not 0<tolerance<=.00501:raise ValueError('Reference tolerance exceeds 0.01 printed precision')
        found=[v for v in com['rows'] if v['profile']==r['reference']['profile'] and v['station']==mapping['station'] and v['node_type']==mapping['node_type'] and v['updn_argument']==0]
        if len(found)!=1:raise ValueError('Published output location does not match one native node')
        actual=number(found[0]['metrics'].get(mapping['variable']));published=float(ref[mapping['column']])
        if not finite(published) or published==-9999:raise ValueError('Reference is missing')
        delta=actual-published if actual is not None else None
        rows.append(dict(**mapping,published=published,actual=actual,delta=delta,passed=delta is not None and abs(delta)<=tolerance))
    result=dict(schema_version='public_csv_comparison_1.0',status='PASS_AT_PUBLISHED_PRECISION' if all(x['passed'] for x in rows) else 'MISMATCH_REQUIRES_REVIEW',
        created_utc=utc(),run_id=hyd['run_id'],sources=[item(rp),item(archive),item(sp),item(solver/'manifest.json'),hyd['raw_controller']],
        profile=r['reference']['profile'],row_selector=r['reference']['row_selector'],rows=rows,
        hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED',limitations=r['limitations'])
    save(out,result);return result
