from .common import runtime_scratch
"""Local source text and parameter candidates. Source contents are never instructions."""
import re
from pathlib import Path

from .common import ROOT, intact, item, read, safe_path, save, utc


def extract(source_path, output):
    source=safe_path(ROOT,source_path);suffix=source.suffix.lower();blocks=[];limitations=[]
    if suffix=='.pdf':
        from pypdf import PdfReader
        pdf=PdfReader(source)
        for i,page in enumerate(pdf.pages):
            blocks.append(dict(locator=f'pdf_page:{i+1}',text=page.extract_text() or ''))
        limitations.append('PDF text extraction does not verify diagrams or scanned numbers; visually review original pages')
    elif suffix=='.docx':
        from docx import Document
        doc=Document(source)
        for i,node in enumerate(doc.element.body):
            if node.tag.endswith('tbl'):
                for j,row in enumerate(node.xpath('./w:tr')):
                    cells=[' '.join(cell.xpath('.//w:t/text()')) for cell in row.xpath('./w:tc')]
                    blocks.append(dict(locator=f'docx_body:{i+1}/row:{j+1}',text=' | '.join(cells)))
            else:blocks.append(dict(locator=f'docx_body:{i+1}',text=' '.join(node.xpath('.//w:t/text()'))))
        limitations.append('DOCX body/table locators are not rendered page numbers; drawings and images require visual review')
    elif suffix in ['.txt','.md']:
        for i,line in enumerate(source.read_text(encoding='utf-8-sig').splitlines()):
            blocks.append(dict(locator=f'line:{i+1}',text=line))
    else:
        raise ValueError('Supported text sources: PDF, DOCX, UTF-8 TXT/MD; images require a separate visual review')
    result=dict(schema_version='1.0',status='EXTRACTED_NOT_REVIEWED',created_utc=utc(),source=item(source,'original_document'),
                blocks=blocks,empty_blocks=[b['locator'] for b in blocks if not b['text'].strip()],limitations=limitations)
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Preserve prior extraction; choose a new output')
    save(out,result);return result


def verified_text(path):
    path=safe_path(ROOT,path);data=read(path)
    if data.get('status')!='EXTRACTED_NOT_REVIEWED' or not intact([data['source']]):
        raise ValueError('Source text evidence missing or original changed')
    # Re-extract in memory via the same reader to reject hand-edited derived text.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='review_evidence_',dir=runtime_scratch()) as temp:
        actual=extract(ROOT/data['source']['path'],Path(temp)/'text.json')
        if actual['blocks']!=data['blocks']:
            raise ValueError('Extracted text differs from the original document')
    return data


def parameters(evidence_path,spec_path,output):
    data=verified_text(evidence_path);spec=read(safe_path(ROOT,spec_path));fields=[]
    if spec.get('schema_version')!='1.0' or not spec.get('purpose'):
        raise ValueError('Parameter specification requires schema_version and purpose')
    names=[r['name'] for r in spec['fields']]
    if len(set(names))!=len(names):raise ValueError('Duplicate parameter name')
    for field in spec['fields']:
        pattern=re.compile(field['pattern'],re.I|re.M)
        if 'value' not in pattern.groupindex:raise ValueError('Each pattern requires a named value capture')
        matches=[]
        for b in data['blocks']:
            if field.get('locators') and b['locator'] not in field['locators']:continue
            for match in pattern.finditer(b['text']):
                value=match.group('value');unit=match.groupdict().get('unit')
                matches.append(dict(raw_value=value,unit=unit,locator=b['locator'],character_span=list(match.span()),
                    quote=match.group(0),evidence_class='reported_candidate',review_status='UNREVIEWED',vertical_datum=None))
        fields.append(dict(name=field['name'],required=field.get('required',True),value=None,
                           status='MISSING' if not matches else ('CANDIDATE_REQUIRES_REVIEW' if len(matches)==1 else 'AMBIGUOUS'),
                           candidates=matches))
    result=dict(schema_version='1.0',created_utc=utc(),status='CANDIDATES_NOT_MODEL_INPUTS',
                sources=[item(safe_path(ROOT,evidence_path)),data['source'],item(safe_path(ROOT,spec_path))],fields=fields,
                limitations=['Candidate text must be reviewed against source graphics/context and site identity',
                             'Missing fields remain null; no defaults or geometry inferred',
                             'Parameter extraction does not change project inputs or grant conditional authorization'])
    out=safe_path(ROOT,output)
    if out.exists():raise ValueError('Choose a new candidate output')
    save(out,result);return result
