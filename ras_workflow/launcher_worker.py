"""Owned launcher worker: fixed operations, actual solver/results, durable log."""
import os
import sys
from .common import ROOT, read, rel, safe_path, save, unique_id, utc


def prepare_example(entry):
    from .launcher import EXAMPLES, remember
    from .public_case import prepare
    if entry['recipe'] not in [v[1] for v in EXAMPLES.values()]:raise ValueError('Unknown public example')
    project=safe_path(ROOT,entry['project'])
    if project.is_file() and (project.parent/'preparation.json').is_file():return
    if project.parent.exists():
        # Preserve an interrupted preparation, including a project written before its receipt.
        entry.setdefault('preparation_attempts',[]).append(rel(project.parent))
        project=project.parent.parent/(entry['id']+'__prepare_'+unique_id())/'project.json'
        entry['project']=rel(project);remember(entry)
    prepare(entry['recipe'],project.parent,True)


def main(record):
    path=safe_path(ROOT,record)
    if not path.is_relative_to(ROOT/'status/launcher/jobs') or path.name!='job.json':raise ValueError('Invalid launcher job')
    job=read(path);job['pid']=os.getpid();entry=job['entry'];code=1
    def phase(value):job['phase']=value;save(path,job);print(value,flush=True)
    try:
        if entry.get('recipe'):
            phase('PREPARING_PUBLISHED_INPUTS');prepare_example(entry)
        from .cli import run_with_intake
        phase('TERRAIN_INPUTS_SOLVER_REPORTS');code=run_with_intake(entry['project'],entry['scenario'],interactive=False,no_browser=True)
        from .intake import resolve
        project=resolve(entry['project']);state=read(project.parent/'state.json')
        if state.get('latest_summary'):
            summary_data=read(ROOT/state['latest_summary']['path'])
            if summary_data.get('errors'):job['error']='\n'.join(map(str,summary_data['errors']))
        if entry.get('recipe') and state.get('calculation_status')=='COMPUTED':
            from .public_case import compare
            from .report import generate
            from .site_delivery import generate as delivery
            phase('COMPARING_PUBLISHED_RESULTS')
            summary=ROOT/state['latest_summary']['path'];out=path.parent/'reference';comparison=out/'comparison.json'
            result=compare(entry['recipe'],summary,comparison);job['comparison_status']=result['status']
            generate(summary,out/'reports',comparisons=[comparison]);delivery(summary,out/'delivery')
        job.update(status=state.get('workflow_status','FAILED'),exit_code=code,finished_utc=utc())
    except Exception as e:
        import traceback
        traceback.print_exc();job.update(status='FAILED',error=str(e),exit_code=1,finished_utc=utc());code=1
    save(path,job)
    return code


if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
