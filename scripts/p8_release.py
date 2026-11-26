"""Exercise formal review using independent browser profiles and an offline comment."""
from pathlib import Path
from tempfile import TemporaryDirectory

from ras_workflow import app_core as core, team_review, team_delivery
from ras_workflow.common import ROOT, read, save, sha
from midway_release import need, page_action
from p5_release import open_packages


def run(gate):
    out=gate/'p8';out.mkdir(exist_ok=True)
    record=dict(status='RUNNING',human='DEFERRED',cross_machine='DEFERRED')
    receipt=out/'release.json'
    dex=read(gate/'p4/release.json')
    base=dex['baseline']
    modeler='Local modeler context';reviewer='Separate offline review context'
    def state(key):
        return team_review.inspect(key)
    def expect_rejection(key,body,reason):
        try:team_review.decide(key,body)
        except ValueError as err:
            need(reason in str(err),'Unrelated rejection: '+str(err));return str(err)
        raise ValueError('Unexpected successful review operation')
    try:
        page_action(base,'p8-team-submit',actor=modeler,note='Review the observed stage at Dexter RS 500.')
        original=state(base);need(original['state']=='SUBMITTED','Submission did not persist')
        with TemporaryDirectory(dir=out) as directory:
            form=Path(page_action(base,'p8-team-form',directory=directory,run_id=original['edition']['run']))
            filename=page_action(None,'p8-offline-reply',url_override=form.as_uri(),directory=directory,
                                 run_id=original['edition']['run'],actor=reviewer,station='500',dep='observations',
                                 note='Return the matching field visit at RS 500. Recheck stage uncertainty.')
            comment=read(filename)
            record['wrong_edition']=expect_rejection(dex['revision'],comment,'Different edition')
            page_action(base,'p8-team-import',file=filename)
            record['conflict']=expect_rejection(base,comment,'Review changed')
        need(state(base)['state']=='RETURNED','Expected a returned submission')
        old=core.model(dex['revision'])
        source=read(ROOT/old['summary']['path'])['configuration']
        # The same original field return belongs to the already-computed P4 branch.
        # Create an independent editable edition before returning the original evidence anew.
        fresh=page_action(base,'river-revision')
        page_action(fresh,'survey-solve')
        revised=page_action(fresh,'field-return',kind='observation',
            file=str(ROOT/source['returned_observations'][0]['path']),
            document=str(ROOT/source['returned_observation_originals'][0]['path']),expect='500')
        page_action(revised,'survey-solve')
        stage=state(revised)
        need(stage['decisions'][-1]['changed']==['observations'],'Unrelated station inputs were invalidated')
        page_action(revised,'p8-team-submit',actor=modeler,note='Submitted with the original observation and its uncertainty limit.')
        need(state(base)['state']=='SUPERSEDED','Returned edition was not superseded')
        page_action(revised,'p8-team-review',actor=reviewer,note='Diagnostic review complete. Measurement uncertainty is still required.',
                    station='500',dep='observations')
        transfer=ROOT/page_action(revised,'transfer-current',selection='Select this edition for diagnostic review only.')
        pair=open_packages(transfer)
        page_action(revised,'p8-team-deliver',actor='Local issue lead',note='Issue for diagnostic review within the stated project purpose.')
        issued=state(revised);event=issued['history'][-1]
        client=ROOT/event['handoff']['client'];internal=ROOT/event['handoff']['internal']
        need(event['state']=='DELIVERED' and pair['run']==issued['edition']['run'],'Incorrect issue run')
        inv=read(internal/'INTERNAL.json')
        excluded={r['sha256'] for r in inv['source_packages']['Complete'] if r['distribution']=='internal'}
        # Identical data may have a separate public role (e.g. a source DEM and the packaged terrain).
        # A returned field original must never appear in either outbound package.
        private={r['sha256'] for r in source['returned_observation_originals']}
        need(private<=excluded,'Internal scope lost the original observation')
        outbound={sha(p) for p in client.rglob('*') if p.is_file()}
        need(private.isdisjoint(outbound) and not (client/'Complete/Sources').exists(),'Internal field evidence leaked')
        from pypdf import PdfReader
        for lang in ('CN','EN'):
            doc=client/'Complete/Reports'/('Report_'+lang+'.pdf')
            need(len(PdfReader(doc).pages)>0 and sha(doc)==sha(transfer/'Complete/Reports'/doc.name),'Wrong language report or edition')
        for pack in ('Complete','Minimal'):
            need(sha(next((client/pack/'HEC_RAS').glob('*.p01.hdf')))==pair['hdf_sha256'],'Wrong outbound native result')
        prior=issued['history']
        page_action(revised,'p8-team-withdraw',actor='Local issue lead',note='Exercise a post-issue withdrawal in this isolated test.')
        final=state(revised)
        need(final['history'][:-1]==prior and final['state']=='WITHDRAWN','History changed during withdrawal')
        record.update(status='PASSED',original=base,revision=revised,run=pair['run'],pair=pair,original_pair=str(transfer),
                      client=str(client),internal=str(internal),invalidated=['observations'],excluded_private_hashes=sorted(private),
                      history=[{k:r[k] for k in ('sequence','action','state','actor','token','edition')} for r in final['history']])
    except Exception as exc:
        record.update(status='FAILED',error=str(exc));raise
    finally:save(receipt,record)
    return receipt
