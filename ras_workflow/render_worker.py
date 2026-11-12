"""Owned headless document conversion. Parent assigns a Job Object before GO."""
import shutil
import subprocess
import sys
from pathlib import Path
from .common import ROOT, intact, item, read, rel, safe_path, save, sha, utc, unique_id


def main():
    if sys.stdin.readline().strip() != 'GO': raise RuntimeError('Worker has no ownership handshake')
    request = read(safe_path(ROOT, sys.argv[1])); out = safe_path(ROOT, request['output'])
    if not intact([request['docx']]): raise ValueError('DOCX changed before rendering')
    exe = Path(request['tools']['libreoffice']['path'])
    if sha(exe) != request['tools']['libreoffice']['sha256']: raise ValueError('LibreOffice changed')
    docx = ROOT/request['docx']['path']
    # Deep Windows job paths can exceed LibreOffice's profile/backend path limit.
    # Give each conversion a short, owned workspace and copy exact DOCX bytes.
    work = ROOT/'.tools/lo'/unique_id(); work.mkdir(parents=True, exist_ok=False)
    profile = work/'profile'; profile.mkdir()
    source = work/'document.docx'; shutil.copyfile(docx, source)
    if sha(source) != request['docx']['sha256']: raise ValueError('Conversion input copy mismatch')
    pdf = work/'document.pdf'
    command = [str(exe), '-env:UserInstallation='+profile.resolve().as_uri(), '--headless', '--norestore',
               '--convert-to', 'pdf:writer_pdf_Export', '--outdir', str(work), str(source)]
    r = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       creationflags=subprocess.CREATE_NO_WINDOW)
    print(r.stdout); print(r.stderr, file=sys.stderr)
    save(out/'conversion.json', dict(command=command, returncode=r.returncode, stdout=r.stdout, stderr=r.stderr,
         work=rel(work), copied_docx=item(source), finished_utc=utc()))
    if r.returncode or not pdf.is_file() or pdf.read_bytes()[:5] != b'%PDF-': raise RuntimeError('LibreOffice did not produce a new valid PDF')
    import pypdfium2 as pdfium
    from pypdf import PdfReader
    pages = []
    with pdfium.PdfDocument(pdf) as document:
        count = len(document)
        if count < 1 or count != len(PdfReader(pdf).pages): raise ValueError('PDF page counts differ')
        for i in range(count):
            page = document[i]
            # Consistent 2000 pixel long edge, independent of PDF paper size.
            bitmap = page.render(scale=2000/max(page.get_size()))
            path = out/('page-'+str(i+1)+'.png')
            bitmap.to_pil().save(path); bitmap.close(); page.close(); pages.append(item(path))
    dest = docx.with_suffix('.pdf')
    if dest.exists(): raise ValueError('Refusing to overwrite an existing delivered PDF')
    shutil.copyfile(pdf, dest)
    save(out/'render_manifest.json', dict(status='RENDERED_PENDING_VISUAL_REVIEW', docx=request['docx'], pdf=item(dest),
         pages=pages, tools=request['tools'], conversion=item(out/'conversion.json'), command=command, finished_utc=utc()))


if __name__ == '__main__': main()
