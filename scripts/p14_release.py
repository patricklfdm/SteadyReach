"""Verify one blinded field-to-client browser journey on the acceptance workstation."""
import argparse
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from p4_release import run as field_journey
from midway_release import ROOT, need, page_action
from ras_workflow import app_core, team_review
from ras_workflow.common import read, save, sha, unique_id
from pypdf import PdfReader


def finish(record, out):
    source = read(record)
    need(source['status']=='PASSED', 'Complete the original field-to-revision journey')
    key = source['revision']
    model = app_core.model(key)
    edition = source['run']
    report = read(Path(source['handoff'])/'Complete/Reports/report_data.json')
    brief = report['edition_brief']
    need(brief['run_id']==edition, 'Incorrect report run')
    page = json.loads(page_action(key,'p14-read'))
    for lang in ('en','zh'):
        need(page[lang]==[row[lang] for row in brief['rows']], 'Page and report differ in '+lang)
    page_action(key,'p8-team-submit',actor='Isolated modeler',note='Submit the field comparison for diagnostic review.')
    page_action(key,'p8-team-review',actor='Isolated reviewer',note='Request vertical accuracy before field acceptance.',station='500',dep='observations')
    page_action(key,'p8-team-deliver',actor='Isolated lead',note='Issue for diagnostic review and survey follow-up.')
    issue=team_review.inspect(key)['history'][-1]['handoff']
    client=ROOT/issue['client']
    private={r['sha256'] for r in report['summary']['configuration']['returned_observation_originals']}
    need(bool(private), 'Expected an original field return')
    pdfs={}
    with TemporaryDirectory(dir=out) as temp:
        detached=Path(temp)/'Client'
        shutil.copytree(client,detached)
        inventory=read(detached/'CLIENT.json')
        need(inventory['edition']['run']==edition,'Incorrect client edition')
        for lang,code,note in [('en','EN','Start_EN.txt'),('zh','CN','Start_zh-CN.txt')]:
            opened=page_action(None,'p14-client-note',url_override=(detached/note).as_uri(),run_id=edition)
            pdf=detached/f'Complete/Reports/Report_{code}.pdf'
            cover=PdfReader(pdf).pages[0].extract_text()
            flat=lambda s: ''.join(s.split())
            for row in brief['rows']:
                need(row[lang] in opened and flat(row[lang]) in flat(cover),'Client or PDF first page differs: '+row['heading'][lang])
            need(edition in flat(cover),'Native run missing from cover')
            pdfs[lang]=sha(pdf)
        for pack in ('Complete','Minimal'):
            from ras_workflow.site_delivery import verify
            verify(detached/pack)
            need(sha(next((detached/pack/'HEC_RAS').glob('*.p01.hdf')))==source['native_hdf']['sha256'],'Wrong client HDF')
        need(private.isdisjoint({sha(p) for p in detached.rglob('*') if p.is_file()}),'Private field original in outbound folder')
    result=dict(status='PASSED',journey=str(record),run=edition,baseline_run=source['baseline_run'],
                client=str(client),native=source['native_hdf'],brief=brief,pdfs=pdfs,
                private_originals_excluded=sorted(private),human='DEFERRED',cross_machine='DEFERRED')
    save(out/'release.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('survey','observation','imagery','journey'):
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    out=ROOT/'status/p14'/unique_id()
    out.mkdir(parents=True)
    record=args.journey
    if record is None:
        if not all((args.survey,args.observation,args.imagery)):
            parser.error('Specify survey, observation and imagery from the frozen Dexter inputs')
        field_journey(args.survey,args.observation,args.imagery,out/'journey')
        record=out/'journey/release.json'
    finish(record.resolve(),out)
    print(out/'release.json',flush=True)
