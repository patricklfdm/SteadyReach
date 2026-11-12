"""Real, isolated software smoke checks. These are never site/solver results."""
from pathlib import Path
import subprocess
from .common import ROOT, item, save, unique_id


def run(tools_config=None, *, reports=True, qgis=True):
    folder=ROOT/'status/environment_checks'/unique_id()
    folder.mkdir(parents=True,exist_ok=False)
    result={'scope':'Software smoke checks only; no hydraulic calculation or engineering acceptance',
            'folder':str(folder),'reports':{'status':'SKIPPED'},'qgis':{'status':'SKIPPED'}}
    if reports:
        try:
            from docx import Document
            from pypdf import PdfReader
            from .report_tools import render
            doc=Document();doc.add_heading('Environment check',0)
            doc.add_paragraph('Software validation only. No hydraulic or site results.\n环境检查；非水力计算结果。')
            source=folder/'environment.docx';doc.save(source)
            pdf,pages,_=render(source,tools_config)
            text='\n'.join(p.extract_text() or '' for p in PdfReader(pdf).pages)
            if pages<1 or 'Environment check' not in text:raise ValueError('Converted PDF has no expected content')
            result['reports']={'status':'PASSED','pages':pages,'pdf':item(pdf)}
        except Exception as e:result['reports']={'status':'FAILED','error':str(e)}
    if qgis:
        try:
            from .qgis_runtime import environment
            from .common import read
            root,env=environment(tools_config=tools_config)
            with (folder/'qgis.log').open('wb') as log:
                proc=subprocess.run([str(root/'bin/python3.exe'),str(ROOT/'ras_workflow/qgis_environment_worker.py'),str(folder)],
                    cwd=ROOT,env=env,stdout=log,stderr=log,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode:raise RuntimeError('QGIS loading/export failed (exit '+str(proc.returncode)+'); see '+str(folder/'qgis.log'))
            record=read(folder/'qgis_probe.json')
            if record.get('status')!='PASSED':raise ValueError('QGIS probe did not pass')
            if (folder/'environment_qgis.pdf').read_bytes()[:5]!=b'%PDF-':raise ValueError('QGIS PDF missing or invalid')
            result['qgis']={**record,'pdf':item(folder/'environment_qgis.pdf'),'project':item(folder/'environment.qgz')}
        except Exception as e:result['qgis']={'status':'FAILED','error':str(e)}
    save(folder/'probes.json',result)
    return result
