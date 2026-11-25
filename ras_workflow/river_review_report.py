"""Link the current result's reviewed alternatives and field records to regenerated reports."""
from .common import ROOT, intact, item, read, safe_path
from .river_observations import current, parse, screen
from .study import reviewed


def collect(summary_path, summary):
    from .river_comparison import comparison, native_sections
    ref=item(summary_path)
    folder=safe_path(ROOT,'projects/'+summary['configuration']['project_id'])
    model_path=folder/'app.json'
    from .survey_events import records
    if not model_path.is_file():return {},[]
    from .app_core import edition_record
    model=edition_record(read(model_path))
    measured,sources=records(summary) if model.get('route')=='survey' or summary['configuration'].get('returned_observations') else ([],[])
    data={'events':measured} if measured else {}
    if model.get('summary')!=ref:return data,sources
    def load(entry):
        if not intact([entry]):raise ValueError('River review evidence changed: '+entry['path'])
        sources.append(entry)
        return read(ROOT/entry['path'])
    if model.get('extent_review'):
        from .extent_review import current as current_extent
        packet=current_extent(model)
        if not packet:raise ValueError('Restore the matching flood-edge source and native runs before regenerating this review')
        sources.append(model['extent_review'])
        if packet['extent']:sources.append(packet['extent'])
        data['extent_review']=dict(event=packet['event'],classification=packet['classification'],
            common_sections=packet['common_sections'],max_wse_change=packet['max_wse_change'],
            cases=[{k:c[k] for k in ('label','run_id','profile','flow_cfs','native_warning_count','matched','total','common_median_abs_m')} for c in packet['cases']])
        if model.get('extent_decision'):
            decision=load(model['extent_decision'])
            if decision['comparison']!=model['extent_review'] or decision['summary']!=ref:raise ValueError('Review decision belongs to another edition')
            data['extent_review']['decision']=decision
    if model.get('river_observations'):
        packet=current(model)
        if not packet:raise ValueError('Field observations differ from their saved source or baseline')
        csv_path=ROOT/packet['source']['path'];raw=parse(csv_path.read_text(encoding='utf-8-sig'))
        rows=screen(raw,summary)
        if rows!=packet['rows']:raise ValueError('Observed quantities differ from their source CSV')
        sources.extend([model['river_observations'],packet['source']])
        data['screen']=rows
        events={}
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
            events[spec['event'], spec['date']] = [dict(r,profile=spec['profile']) for r in measured]
        data.setdefault('events',[]).extend(row for event_rows in events.values() for row in event_rows)
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
            data['comparison_width_ft']=read(ROOT/result['study']['path']).get('maximum_width_ft')
            data['changed_ends']=[dict(rs=r['rs'],case=k,side=side,stage=v['stage_ft'],end=v['ends_ft'][i],delta=v['delta_wse_ft'],share=v['ob_percent'][i],baseline_share=r['variants']['baseline']['ob_percent'][i]) for r in rows for k,v in r['variants'].items() for i,side in enumerate(('L','R')) if v['new_wet'][i]]
            data['new_ends']={k:[r['rs']+' '+side for r in rows for side,new in zip(('L','R'),r['variants'][k]['new_wet']) if new] for k in ('fixed','rotated')}
    if model.get('latest_warning_study'):
        result=load(model['latest_warning_study'])
        if result.get('baseline')==ref and result.get('status')=='REVIEW_REQUIRED':
            from .warning_study import assessment
            reviewed(result['study']['path'],result['review']['path'])
            sources.extend([result[k] for k in ('study','review','execution')])
            records={c['id']:c for c in result['cases']}
            frames=[]
            baseline_stages=None
            for key in dict.fromkeys(('baseline',result['lowest_count'],result['recommended'])):
                saved=load(records[key]['audit'])
                native=load(saved['summary'])
                actual=assessment(native,saved['summary'],baseline_stages)
                if actual!=saved or saved['metrics']!=records[key]['metrics']:
                    raise ValueError('Warning review differs from native evidence')
                if key=='baseline':
                    baseline_stages=saved['stages']
                sources.extend([saved['hdf'],saved['native_file'],native['hydraulics']['raw_controller']])
                frames.append(dict(id=key,metrics=actual['metrics']))
            data['warning_review']=dict(frames=frames,lowest=result['lowest_count'],recommended=result['recommended'])
    if sources and not intact(sources):raise ValueError('River review source is incomplete or has changed')
    return data,list({x['path']:x for x in sources}.values())
