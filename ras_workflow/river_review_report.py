"""Link the current result's reviewed alternatives and field records to regenerated reports."""
from .common import ROOT, intact, item, read, safe_path
from .river_observations import current, parse, screen
from .study import reviewed


def collect(summary_path, summary):
    from .river_comparison import comparison, native_sections
    ref=item(summary_path)
    folder=safe_path(ROOT,'projects/'+summary['configuration']['project_id'])
    model_path=folder/'app.json'
    if not model_path.is_file():return {},[]
    model=read(model_path)
    if model.get('summary')!=ref:return {},[]
    data={};sources=[]
    def load(entry):
        if not intact([entry]):raise ValueError('River review evidence changed: '+entry['path'])
        sources.append(entry)
        return read(ROOT/entry['path'])
    if model.get('river_observations'):
        packet=current(model)
        if not packet:raise ValueError('Field observations differ from their saved source or baseline')
        csv_path=ROOT/packet['source']['path'];raw=parse(csv_path.read_text(encoding='utf-8-sig'))
        rows=screen(raw,summary)
        if rows!=packet['rows']:raise ValueError('Observed quantities differ from their source CSV')
        sources.extend([model['river_observations'],packet['source']])
        data['screen']=rows
        events=[]
        for entry in model.get('observed_event_history',[]):
            result=load(entry)
            if result.get('observations')!=packet['source'] or result.get('baseline')!=ref:continue
            plan=load(result['study']);reviewed(result['study']['path'],result['review']['path'])
            sources.extend([result['review'],result['execution']])
            native=load(result['summary'])
            spec=plan['event']
            match=[r for r in raw if r['event']==spec['event'] and r['date']==spec['date']]
            measured=screen(match,native,spec)
            if measured!=result['rows']:raise ValueError('Event residuals differ from native output')
            sources.extend([native['hydraulic_results'],native['hydraulics']['raw_hdf'],native['hydraulics']['raw_controller']])
            events.extend(measured)
        data['events']=events
    if model.get('latest_geometry_comparison'):
        result=load(model['latest_geometry_comparison'])
        if result.get('status')=='COMPARISON_REQUIRES_REVIEW' and result['summaries'].get('baseline')==ref:
            reviewed(result['study']['path'],result['review']['path'])
            frames={}
            for key,entry in result['summaries'].items():
                native=load(entry)
                frames[key]=native_sections(native)
                sources.extend([native['hydraulic_results'],native['hydraulics']['raw_hdf'],native['hydraulics']['raw_controller']])
            rows,totals=comparison(frames)
            if rows!=result['rows'] or totals!=result['totals']:raise ValueError('Revision comparison differs from native output')
            sources.extend([result[k] for k in ('study','review','table','execution')])
            data['comparison']=totals
            data['changed_ends']=[dict(rs=r['rs'],case=k,side=side,stage=v['stage_ft'],end=v['ends_ft'][i],delta=v['delta_wse_ft'],share=v['ob_percent'][i]) for r in rows for k,v in r['variants'].items() for i,side in enumerate(('L','R')) if v['new_wet'][i]]
            data['new_ends']={k:[r['rs']+' '+side for r in rows for side,new in zip(('L','R'),r['variants'][k]['new_wet']) if new] for k in ('fixed','rotated')}
    if sources and not intact(sources):raise ValueError('River review source is incomplete or has changed')
    return data,list({x['path']:x for x in sources}.values())
