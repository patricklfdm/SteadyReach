"""Freeze a first-use trial's inputs and provide blank operator and recipient records."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

CASES = {
    'pagosa': ('coordinates', 'Boundary influence and conditional reach screening', '边界影响与河段条件性初筛'),
    'midway': ('partial', 'Missing inverts, returned evidence and revision selection', '涵底缺失、补测回传与修订选版'),
    'dexter': ('survey', 'Held-out stage and delivery verification', '独立内点水位与交付核验'),
}


def fingerprint(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def freeze(out, case, release, sources):
    if out.exists():
        raise ValueError('Choose a new pilot folder / 请选择新试点目录')
    manifest=json.loads(release.read_text(encoding='utf-8-sig'))
    if manifest.get('schema')!='steadyreach_release_1' or not re.fullmatch(r'[0-9a-f]{40}',str(manifest.get('git_commit'))):
        raise ValueError('Select the verified RELEASE.json / 请使用已核验的发行清单')
    files=[dict(name=p.name,sha256=fingerprint(p)) for p in sources]
    if not files or len({(r['name'],r['sha256']) for r in files})!=len(files):
        raise ValueError('Select distinct starting records / 请逐一选择起始原件')
    route,en,zh=CASES[case]
    out.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage=Path(tmp)/'pilot';stage.mkdir()
        docs=Path(__file__).resolve().parents[1]/'docs'
        for lang in ('EN','CN'):
            name='FIRST_PILOT_'+lang+'.md'
            (stage/name).write_bytes((docs/name).read_bytes())
        record=dict(case=case,route=route,task=[en,zh],sources=files,release_sha256=fingerprint(release),
                    commit=manifest['git_commit'],protocols={p.name:fingerprint(p) for p in sorted(stage.glob('*.md'))})
        (stage/'protocol.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
        header=['case','route','frozen_protocol_sha256','edition','started','first_pair_verified','evidence_stop','engineer_minutes',
                'machine_seconds','solver_seconds','external_wait_minutes','developer_interventions','blocker_step','expected','actual',
                'assumptions_labelled','use_explained','selected_run','final_disposition']
        with (stage/'scorecard.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=header);writer.writeheader()
            writer.writerow(dict(case=case,route=route,frozen_protocol_sha256=fingerprint(stage/'protocol.json')))
        (stage/'recipient.md').write_text('# Independent recipient / 独立接收人\n\n'+
            '\n\n'.join(k+'  __________' for k in ['Reviewer and date / 复核人及日期','Selected edition and run / 选定版及运行',
            'Minimal and Complete verified / 双包校验','Allowed purpose and location / 用途与位置',
            'Remaining limitation and next action / 限制与下一步','Disposition, owner and date / 结论、负责人及日期'])+'\n',encoding='utf-8')
        stage.rename(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=CASES,required=True)
    for name in ('out','release'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source',type=Path,action='append',required=True)
    args=parser.parse_args()
    freeze(args.out,args.case,args.release,args.source)
    print(args.out)
