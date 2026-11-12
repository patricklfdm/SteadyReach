"""User criteria and edition changes, evaluated against verified native results."""
from tempfile import TemporaryDirectory
from pathlib import Path
from .common import ROOT, finite, intact, item, read, safe_path

METRICS={'headwater_wse_ft':('ft','Headwater elevation','涵前水位'),
         'tailwater_wse_ft':('ft','Tailwater elevation','涵后水位'),
         'road_freeboard_ft':('ft','Road margin','道路余高')}

def changes(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return [r for k in sorted(set(a)|set(b)) for r in changes(a.get(k),b.get(k),path+'.'+k)]
    if a==b:return []
    return [dict(field=path.lstrip('.'),previous=a,current=b)]

def evaluate(summary_path,context):
    path=safe_path(ROOT,summary_path);summary=read(path);hyd=summary.get('hydraulics')
    if not hyd:raise ValueError('Report criteria require computed results')
    if not hyd.get('unit') or not hyd.get('datum'):raise ValueError('Report criteria require explicit calculation units and datum')
    from .qa import verified_profiles,compare
    verified_profiles(hyd)
    if summary.get('hydraulic_results') and (not intact([summary['hydraulic_results']]) or read(ROOT/summary['hydraulic_results']['path'])!=hyd):raise ValueError('Summary differs from the sealed hydraulic extraction')
    if context.get('schema_version')!='report_context_1.0' or context.get('summary')!=item(path):raise ValueError('Report context must bind the exact summary')
    for key in ['purpose','reviewer']:
        if not isinstance(context.get(key),str) or not 0<len(context[key].strip())<=2000:raise ValueError('Report '+key+' is required')
    criteria=context.get('criteria',[])
    if not isinstance(criteria,list) or len(criteria)>50:raise ValueError('At most 50 criteria are supported')
    profiles={p['profile_id']:p for p in hyd['profiles']};rows=[]
    for c in criteria:
        if not isinstance(c,dict) or c.get('metric') not in METRICS or c.get('profile') not in profiles:raise ValueError('Unknown criterion profile or metric')
        if c.get('operator') not in ['>=','<='] or not finite(c.get('limit')):raise ValueError('Criterion needs a finite limit and >= or <=')
        if c.get('unit')!=hyd['unit'] or c.get('datum')!=hyd['datum']:raise ValueError('Criterion unit/datum must match this calculation')
        if not isinstance(c.get('basis'),str) or not 0<len(c['basis'].strip())<=5000:raise ValueError('Criterion source/basis is required; no design default is supplied')
        value=profiles[c['profile']]['metrics'].get(c['metric'])
        status='UNAVAILABLE' if not finite(value) else ('SATISFIED' if (value>=c['limit'] if c['operator']=='>=' else value<=c['limit']) else 'NOT_SATISFIED')
        rows.append(dict(c,value=value,status=status))
    result=dict(purpose=context['purpose'],reviewer=context['reviewer'],criteria=rows,
        engineering_acceptance='NOT_ASSESSED',sources=[],previous=None,review=None,edition_changes=None)
    edition=context.get('previous_report')
    if edition:
        if not isinstance(edition,dict) or not intact([edition]):raise ValueError('Previous report changed')
        from .report_catalog import validate
        m=read(ROOT/edition['path']);validate(m['summary']['path'],edition['path'])
        olddata=read(ROOT/m['data']['path'])
        if olddata['summary']['hydraulics']['project_id']!=hyd['project_id']:raise ValueError('Previous report belongs to another project')
        oldcontext=olddata.get('context') or {}
        result['edition_changes']=dict(manifest=edition,fields=changes({k:oldcontext.get(k) for k in ['purpose','reviewer','criteria']},{k:result[k] for k in ['purpose','reviewer','criteria']}))
        from .report_catalog import entries
        result['sources'] += [edition]+list(entries(m))
    previous=context.get('previous_summary')
    if previous:
        if not isinstance(previous,dict) or not intact([previous]):raise ValueError('Previous summary changed')
        old=read(ROOT/previous['path'])
        with TemporaryDirectory(dir=ROOT/'status',prefix='edition_compare_') as temp:
            comparison=compare(ROOT/previous['path'],path,Path(temp)/'comparison.json')
        result['previous']=dict(summary=previous,comparison=comparison,
            same_solver_run=old['hydraulics']['run_id']==hyd['run_id'],
            input_changes=changes(old['configuration'],summary['configuration']))
        snapshots=[]
        for hh in [old['hydraulics'],hyd]:
            mp=(ROOT/hh['raw_hdf']['path']).parent.parent/'manifest.json'
            if mp.exists():
                manifest=read(mp);entries=manifest.get('native_before',[])
                if manifest.get('run_id')!=hh['run_id'] or not intact(entries):raise ValueError('Previous/current native input snapshots changed')
                snapshots.append({Path(e['path']).suffix.lower():e['sha256'] for e in entries})
                result['sources'] += [item(mp)]+entries
            else:snapshots.append({})
        result['previous']['native_input_changes']=changes(*snapshots)
        result['sources']+=[previous,old['hydraulics']['raw_hdf'],old['hydraulics']['raw_controller']]
    review=context.get('qa_decisions')
    if review:
        if not isinstance(review,dict) or not intact([review]):raise ValueError('QA decisions changed')
        from .qa_review import validate_decisions,closure_status
        spec=read(ROOT/review['path']);packet=read(ROOT/spec['packet']['path'])
        validate_decisions(spec['packet']['path'],spec)
        if packet['run_id']!=hyd['run_id']:raise ValueError('QA decisions belong to another solver run')
        result['review']=dict(reviewer=spec['reviewer'],closure=closure_status(packet,spec['decisions']),decisions=spec['decisions'])
        result['sources'] += [review,spec['packet']]+packet['sources']+[e for d in spec['decisions'] for e in d.get('evidence',[])]
    return result

def attach(data,summary_path,context_path):
    if not context_path:return
    entry=item(safe_path(ROOT,context_path));context=read(ROOT/entry['path'])
    result=evaluate(summary_path,context);data['context']=result
    data['sources'] += [entry]+result['sources']

def compose(doc,data,tr,num,full=True):
    from .report import table
    c=data.get('context')
    if not c:return
    heading=doc.add_heading(tr('Purpose and user criteria','用途与用户判据'),1 if full else 2)
    if full:heading.paragraph_format.page_break_before=True
    doc.add_paragraph(c['purpose']);doc.add_paragraph(tr('Criteria reviewer: ','判据审核人：')+c['reviewer'])
    doc.add_paragraph(tr('The comparisons below apply only to user-supplied criteria and the stated inputs. Satisfying a numerical criterion does not close hydraulic QA or establish engineering acceptance.',
        '下列对比仅针对用户提供的判据及本次输入条件。满足数值判据不代表水力 QA 闭合，也不代表工程接受。'))
    for r in c['criteria']:
        label=METRICS[r['metric']];status={'SATISFIED':tr('Satisfied','满足'),'NOT_SATISFIED':tr('Not satisfied','不满足'),'UNAVAILABLE':tr('Unavailable','无法判定')}[r['status']]
        table(doc,[tr('Profile / metric','工况 / 指标'),tr('Computed','计算值'),tr('Criterion','判据'),tr('Comparison','对比结果')],
            [[r['profile']+' / '+tr(label[1],label[2]),num(r['value'],3),r['operator']+' '+num(r['limit'],3),status]],[2.3,1.3,1.6,1.5])
        doc.add_paragraph(tr('Basis: ','依据：')+r['basis']+' | '+r['unit']+' | '+r['datum'])
    if not c['criteria']:doc.add_paragraph(tr('No numerical design criteria were supplied.','未提供数值设计判据。'))
    old=c['previous']
    if old:
        doc.add_paragraph(tr('Previous solver run: ','前次求解：')+old['comparison']['baseline_run_id'])
        doc.add_paragraph(tr('Same solver run; this is a report edition, not a rerun.','同一次求解；这是报告版本变化，不是重算。') if old['same_solver_run'] else tr('Distinct solver runs. Differences are current minus previous at matched profiles and sections.','不同求解运行。差值为相匹配工况与断面的本次值减前次值。'))
        table(doc,[tr('Profile','工况'),tr('Change in HW ft','涵前水位变化 ft'),tr('Max XS WSE change ft','最大断面水位变化 ft')],
            [[r['profile'],num(r['delta_hw_ft'],6),num(r['max_matched_xs_delta_wse_ft'],6)] for r in old['comparison']['rows']],[1.4,2.6,2.7])
        fields=[r['field'] for r in old['input_changes']]
        doc.add_paragraph(tr('Changed configuration fields: ','配置变化字段：')+(', '.join(fields) if fields else tr('None. Geometry changes, if any, remain in the bound native input snapshots.','无。几何变化须另查所绑定的原生输入快照。')))
        doc.add_paragraph(tr('Detailed values, unmatched profiles and added/removed sections are retained in report_data.json. Removed sections do not prove issue resolution.','详细值、未匹配工况及新增/移除断面保存在 report_data.json。移除断面不能证明问题解决。'))
        doc.add_paragraph(tr('Changed native input file types: ','发生变化的原生输入文件类型：')+(', '.join(r['field'] for r in old['native_input_changes']) or tr('None recorded','未记录变化')))
    if c.get('edition_changes'):
        doc.add_paragraph(tr('Changed report context fields: ','报告上下文变化字段：')+(', '.join(r['field'] for r in c['edition_changes']['fields']) or tr('None','无')))
    if c['review']:
        doc.add_paragraph(tr('Bound QA review by ','所绑定的 QA 审核人：')+c['review']['reviewer']+' | '+c['review']['closure']['hydraulic_qa_status'])
        from collections import Counter
        for state,count in Counter(d['disposition'] for d in c['review']['decisions']).items():doc.add_paragraph(state+': '+str(count))
