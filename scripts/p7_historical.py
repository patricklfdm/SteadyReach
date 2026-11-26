"""Independently check station-level claims using retained native runs on this workstation."""
import json
from pathlib import Path
import sys

CODE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CODE))
from ras_workflow import common


def inspect(root):
    common.ROOT=root.resolve()
    from ras_workflow.app_revision import compare
    from ras_workflow.hydraulic_confidence import assess
    from ras_workflow.report_studies import collect
    from ras_workflow.result_atlas import native_rows
    from midway_release import need
    results={}
    for name,key in [('Pagosa','site_20261119t082835_2953e3365d'),('Merced','site_20261119t124424_cc9e08fc86')]:
        m=common.read(root/'projects'/key/'app.json');ref=m['summary'];need(common.intact([ref]),'Changed historical summary')
        summary=common.read(root/ref['path']);h=summary['hydraulics'];need(common.intact([h['raw_hdf'],h['raw_controller']]),'Changed native output')
        studies,_=collect(root/ref['path'],summary) if name=='Pagosa' else ([],[])
        comparison=compare(m,summary) if name=='Merced' else None
        import h5py
        from ras_workflow.qa import BASE,number
        rows=[r for r in native_rows(h) if r['profile']=='Q100']
        with h5py.File(root/h['raw_hdf']['path']) as raw:
            result=raw[BASE+'/Cross Sections']
            index=next(i for i,p in enumerate(h['profiles']) if p['profile_id']=='Q100')
            stations=[v['Station'].decode().strip() for v in raw['Results/Steady/Output/Geometry Info/Cross Section Attributes'][:]]
            need([float(r['rs']) for r in rows]==list(map(float,stations)),'Historical station order differs')
            for i,r in enumerate(rows):
                q=number(result['Flow'][index,i]);extra=result.get('Additional Variables')
                splits=[number(extra[k][index,i]) for k in ('Flow Left OB','Flow Right OB')] if extra is not None and all(k in extra for k in ('Flow Left OB','Flow Right OB')) else []
                shares=[100*v/q for v in splits] if q and len(splits)==2 and None not in splits else None
                r['profiles']={'Q100':dict(wse_ft=r['wse_ft'],flow_cfs=q,overbank_percent=shares)}
        diagnostics=common.read(root/h['diagnostics']['path']);need(common.intact([h['diagnostics']]),'Changed diagnostics')
        profile=assess(summary,rows,[],diagnostics,studies,comparison)['profiles'][0];sections=profile['sections']
        if name=='Merced':
            peak=max((r for r in sections if r['revision_wse_change_ft'] is not None),key=lambda r:abs(r['revision_wse_change_ft']))
            split=max((r for r in sections if r['overbank_change_points']),key=lambda r:max(map(abs,r['overbank_change_points'])))
            need(peak['rs']=='3400' and split['rs']=='4700' and abs(peak['revision_wse_change_ft']+5.068)<.002,'Merced distribution or location differs')
            results[name]=dict(run=h['run_id'],stage_peak=peak,split_peak=split)
        else:
            cases={}
            for r in sections:
                for t in r['tests']:
                    if t['kind']=='boundary':cases.setdefault(t['case'],[]).append((r['rs'],t['delta_ft']))
            need(len(cases)>=4 and all(len(rows)==32 for rows in cases.values()),'Boundary sensitivity propagation is incomplete')
            results[name]=dict(run=h['run_id'],boundary_cases=cases)
    return results


if __name__=='__main__':
    print(json.dumps(inspect(Path(sys.argv[1]))))
