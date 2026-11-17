"""Compact bilingual revision interpretation shared by river and culvert reports."""
import json
from .report import table


def value(v):
    if v is None:
        return '—'
    if isinstance(v,(float,int)):
        return f'{v:.8g}'
    text=json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)
    return text if len(text)<=90 else text[:87]+'...'


def compose(doc,data,tr,full):
    comparison=data.get('revision_comparison')
    if not comparison:
        return
    doc.add_heading(tr('What changed from the parent calculation','相对父计算的变化'),1)
    if comparison['status']!='COMPARISON_NOT_ACCEPTANCE':
        doc.add_paragraph(tr('Revision comparison unavailable: ','修订对比不可用：')+str(comparison.get('error',comparison['status'])))
        return
    context=comparison['input_context']
    if context['status']!='VERIFIED':
        doc.add_paragraph(tr('Input and geographic correspondence could not be verified. Same station IDs alone do not establish the same location. ',
                             '尚未核验输入和地理对应；相同断面编号不能单独证明位置一致。')+context.get('error',''))
    else:
        g=context['geometry']
        doc.add_paragraph(tr(
            f"Sections: {g['previous_count']} to {g['current_count']}; {g['changed_sections']} retained sections have changed geometry, {g['moved_centers']} centers moved, and {g['moved_bank_pairs']} bank pairs moved in plan.",
            f"断面数由 {g['previous_count']} 变为 {g['current_count']}；保留断面中 {g['changed_sections']} 条几何改变、{g['moved_centers']} 条中心移动、{g['moved_bank_pairs']} 组岸站平面位置移动。"))
        if g['unverified_centers']:
            doc.add_paragraph(tr('Centers lacking a comparable projected position: ','缺少可比投影位置的断面中心数：')+str(g['unverified_centers']))
        if g.get('unverified_bank_pairs'):
            doc.add_paragraph(tr('Bank pairs lacking comparable map positions: ','缺少可比平面位置的岸站组数：')+str(g['unverified_bank_pairs']))
        if context['interpretation']=='MULTIPLE_INPUT_CHANGES':
            doc.add_paragraph(tr('Geometry and other model inputs changed together. These differences cannot be attributed to section spacing alone; this is not an isolated spacing-convergence test.',
                                 '几何和其他模型输入同时改变，差值不能单独归因于断面加密；本次不属于仅改变间距的收敛检验。'))
        if full and context['input_changes']:
            labels={'boundary_slopes.upstream':tr('Upstream normal-depth slope','上游正常水深坡降'),
                    'boundary_slopes.downstream':tr('Downstream normal-depth slope','下游正常水深坡降'),
                    'channel_n':tr('Channel n','主槽 n'),'overbank_n':tr('Overbank n','漫滩 n'),
                    'flow_regime':tr('Flow regime','流态')}
            table(doc,[tr('Changed input','改变的输入'),tr('Previous','上次'),tr('Current','本次')],
                  [[labels.get(r['field'],r['field']),value(r['previous']),value(r['current'])] for r in context['input_changes'][:12]],[2.7,2.,2.])
            if len(context['input_changes'])>12:
                doc.add_paragraph(tr('All input changes are listed in report_data.json.','完整输入变化见 report_data.json。'))
    for profile in comparison['profiles']:
        maximum=profile.get('maximum_at_verified_centers')
        if maximum:
            doc.add_paragraph(profile['profile']+tr(' maximum |WSE change| at a verified unchanged center: ',' 中心经核验未移动的断面最大绝对水位差：')+
                              f"{abs(maximum['change']):.6f} ft at RS {maximum['station']}"+
                              tr('. Section shape and controls may still differ.','；断面形状和水力控制仍可能不同。'))
        else:
            doc.add_paragraph(profile['profile']+tr(' has no verified coincident-center water-level comparison.',' 无可核验同中心位置的水位对比。'))
    old,now=comparison['diagnostics']['previous'],comparison['diagnostics']['current']
    if old['status']==now['status']=='VERIFIED':
        doc.add_paragraph(tr('Native messages, previous/current: ','原生信息条数，上次／本次：')+str(old['native_messages'])+' / '+str(now['native_messages'])+
                          tr('. Fewer messages do not establish hydraulic acceptance.','；信息减少不代表水力验收通过。'))
    if context['status']=='VERIFIED':
        doc.add_paragraph(tr('The parent calculation and input snapshots are hash-verified.','父计算及输入快照经过哈希核验。'))
    doc.add_paragraph(tr('Available per-section changes, correspondence checks and source references are retained in report_data.json. New geometry needs its own boundary and spacing assessment.',
                         '已取得的逐断面变化、位置对应核验及来源保留于 report_data.json；新几何仍需独立的边界与间距评估。'))
