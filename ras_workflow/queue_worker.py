"""Owned worker: do nothing until the parent assigns the Windows Job Object."""
import os
import sys
import traceback
from pathlib import Path
from .common import ROOT, intact, item, read, save


def main():
    if sys.stdin.readline().strip()!='GO':return 3
    request_path=Path(sys.argv[1]);request=read(request_path);job=request['job']
    if not intact(request['identity']['evidence']['inputs']+request['identity']['evidence']['code']):
        raise ValueError('Queued inputs or code changed before worker start')
    if job.get('tools'):os.environ['HECRAS_WORKFLOW_TOOLS']=str(ROOT/job['tools'])
    receipt=request_path.parent/'attempt_receipt.json'
    from .cli import execute
    code=execute(job['project'],job['scenario'],fresh=request['fresh'],timeout=job.get('solver_timeout_seconds',180),receipt_path=receipt)
    save(request_path.parent/'worker_result.json',dict(exit_code=code,receipt=item(receipt)))
    return code


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        traceback.print_exc();raise SystemExit(1)
