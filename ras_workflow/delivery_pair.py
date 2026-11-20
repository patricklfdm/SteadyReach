"""Trace the two offline folders back to the same HDF, reports and QGIS export."""
import argparse
import json
from pathlib import Path
from xml.etree import ElementTree
from .common import read,sha


def verified_member(root,name,expected):
    root=Path(root).resolve()
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or sha(path)!=expected:
        raise ValueError('Delivery fingerprint mismatch: '+name)
    return path


def check(full,minimal):
    full,minimal=Path(full),Path(minimal)
    evidence=full/'Evidence'
    archived=evidence/'summary.original.json';s=read(archived);h=s['hydraulics']
    run=read(evidence/'run_manifest.original.json')
    reports=read(evidence/'report_manifest.original.json')
    if run['run_id']!=h['run_id'] or reports['summary']['sha256']!=sha(archived):
        raise ValueError('Report and native run identities disagree')
    data_ref=reports['data']
    data=read(verified_member(full/'Reports',Path(data_ref['path']).name,data_ref['sha256']))
    if data['summary']!=s:raise ValueError('Packaged report data uses a different summary')
    for folder in (full,minimal):
        for entry in run['native_after']+[h['raw_hdf']]:
            verified_member(folder/'HEC_RAS',Path(entry['path']).name,entry['sha256'])
    report_names=[]
    for edition in reports['reports']:
        for kind in ('pdf','docx'):
            entry=edition[kind];name=Path(entry['path']).name
            verified_member(full/'Reports',name,entry['sha256']);report_names.append(name)
    languages={e['language'] for e in reports['reports'] if e['detail']=='full'}
    if languages!={'en','zh-CN'}:raise ValueError('Both full reports are required')
    mapped=(full/'GIS_Project.qgz').is_file()
    if mapped:
        flow_labels=[f"{p['profile_id']}: {p['flow_cfs']:g} cfs" for p in h['profiles']]
        for lang in ('EN','CN'):
            layout=full/'Layouts'/('Exhibit_'+lang+'.qpt')
            labels='\n'.join(val for node in ElementTree.parse(layout).iter() for val in node.attrib.values())
            if h['run_id'] not in labels or any(flow not in labels for flow in flow_labels):
                raise ValueError('QGIS layout belongs to a different run or profile: '+lang)
            for suffix in ('pdf','png'):
                if not (full/'Graph'/('Exhibit_'+lang+'.'+suffix)).is_file():raise ValueError('Missing exhibit: '+lang)
        verified_member(minimal,'Graph/Exhibit_EN.pdf',sha(full/'Graph/Exhibit_EN.pdf'))
    return dict(run_id=h['run_id'],summary_sha256=sha(archived),native_hdf_sha256=h['raw_hdf']['sha256'],
                report_manifest_sha256=sha(evidence/'report_manifest.original.json'),mapped=mapped,reports=report_names)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('complete',type=Path);cli.add_argument('minimal',type=Path)
    args=cli.parse_args()
    for folder in (args.complete,args.minimal):
        for row in read(folder/'PACKAGE_MANIFEST.json')['files']:verified_member(folder,row['path'],row['sha256'])
    print(json.dumps(check(args.complete,args.minimal),indent=2))
