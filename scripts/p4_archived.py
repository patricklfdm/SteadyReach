"""Read-only regression against the archived Pagosa and Merced native output."""
import json
from pathlib import Path
import subprocess
import sys

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))


def run(archive):
    from ras_workflow import common
    common.ROOT=archive.resolve()
    from ras_workflow.app_revision import compare
    from ras_workflow.app_check_batch import question_result
    from ras_workflow.report_studies import collect
    from ras_workflow.river_review import response
    from ras_workflow.qa import THRESHOLDS
    def project(key):
        m=common.read(archive/'projects'/key/'app.json')
        if not common.intact([m['summary']]):raise ValueError('Archived summary differs')
        return m,common.read(archive/m['summary']['path'])
    m,s=project('site_20261119t082835_2953e3365d')
    studies,_=collect(archive/m['summary']['path'],s)
    study,=[x for x in studies if len(response([x]))==4 and all(r['paths'][0].startswith('boundary_slopes.') for r in response([x]))]
    ref=study['analysis']
    plan=dict(options=dict(question='boundary'),steps=[dict(id='sensitivity')])
    bounds=question_result(plan,dict(sensitivity=dict(status='COMPLETED',analysis=ref)),[study])
    if len(bounds['cases'])!=4 or not all(r['compared']==32 for r in bounds['cases']) or bounds['status']!='FIELD_REVIEW_BEFORE_ANOTHER_BATCH':
        raise ValueError('Missing spatial boundary effects in Pagosa')
    m,s=project('site_20261119t124424_cc9e08fc86')
    comp=compare(m,s)
    js="""const fs=require('node:fs'),vm=require('node:vm');let ctx=vm.createContext({});vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);console.log(JSON.stringify(ctx.priorityRows({},JSON.parse(fs.readFileSync(0,'utf8')))));"""
    row=json.loads(subprocess.check_output(['node','-e',js,str(CODE/'ras_workflow/templates/app_guidance.js')],
                   input=json.dumps(comp).encode(),cwd=CODE))[0]
    if not all(v in row['en'] for v in ('3400','-5.068','4700','70.14%','69')):
        raise ValueError('Merced warning decrease must be shown with stage and floodplain flow changes')
    return dict(pagosa=bounds,merced=row,sensitivity_threshold_ft=THRESHOLDS['sensitivity_hw_ft'],
                mode='archived native results; no new calculations')


if __name__=='__main__':
    print(json.dumps(run(Path(sys.argv[1])),ensure_ascii=True))
