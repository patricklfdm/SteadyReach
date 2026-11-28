"""Select the next investigation from edition-bound evidence, without changing its score."""
from .common import finite


def recommendation(decision, steps=(), comparison=None, studies=()):
    review = (comparison or {}).get('review') or {}
    rows = decision.get('rows') or []
    outstanding = [row for row in rows if row['state'] in ('exceeded', 'missing')]
    field_rows = [r for r in outstanding if r['state'] == 'exceeded'
                  and (r.get('action') or {}).get('tool') == 'observations']
    def excess(row):
        f = row.get('field_check') or {}
        return abs(f['residual_ft'])-f['limit_ft'] if f else -1
    observation = max(field_rows, key=excess, default=None)
    spacing = next((s for s in reversed(studies or []) if s.get('convergence')), {})
    conv = spacing.get('convergence') or {}
    limit = conv.get('threshold_ft')
    profile = ((observation or {}).get('field_check') or {}).get('profile')
    stable = finite(limit) and any(r.get('profile')==profile and r.get('status')=='STABLE_AT_REVIEW_THRESHOLD'
                                   for r in conv.get('rows',[]) if profile)
    heading = dict(en='Next engineering decision', zh='下一项工程判断')

    def result(code, action, evidence, en, zh):
        return dict(code=code, heading=heading, action=action, en=evidence['en']+' '+en,
                    zh=evidence['zh']+zh)

    paired = review.get('field_regression')
    if paired:
        return result('KEEP_REFERENCE', paired['action'], paired,
                      'Reopen edition selection after a single evidenced change has been tested.',
                      '取得一项有依据的输入改动并单独检验后，再比较选版。')
    if review.get('field_regression_error'):
        return result('RESTORE_COMPARISON', dict(tool='comparison'), decision,
                      'Restore the paired observations before using warning counts to rank these editions.',
                      '先恢复两版对应的实测记录，再解释警告数的变化。')
    if observation:
        note = (f'The tested spacing series met its {limit:g} ft numerical threshold. ' if stable else '')
        cn = (f'已试算的加密序列达到 {limit:g} ft 数值门槛。' if stable else '')
        facts = observation.get('field_check')
        evidence = observation
        if facts:
            values = f"RS {facts['rs']} · {facts['residual_ft']:+.3f} ft"
            evidence = dict(en=f"{values} modeled minus observed (limit {facts['limit_ft']:g} ft).",
                            zh=f"{values} 为计算减实测（限值 {facts['limit_ft']:g} ft）。")
        return result('CHECK_FIELD_CONTROL', observation['action'], evidence,
                      note+'Pause fitting. Verify event timing, vertical tie and the outlet control. If these agree, request the bed section or flow split at the discrepant reach before rerunning.',
                      cn+'暂停调参。先核对事件时刻、高程联测和出口控制；若均吻合，再补偏差河段的水下断面或分流测量后重算。')
    path_change = next((r for r in review.get('investigation', []) if r.get('kind') == 'overbank_share'), None)
    if path_change and 'CHECK_WATER_LEVEL_CHANGE' in review.get('flags', []):
        return result('VERIFY_FLOW_PATH', dict(tool='comparison'), path_change,
                      'Check connected overbank flow against adjacent sections and opening surveys before accepting the revision.',
                      '选版前，沿相邻断面核对漫滩通道是否连通，并与开口测量比对。')
    if outstanding and all(r['state']=='missing' and (r.get('action') or {}).get('tool')=='observations' for r in outstanding):
        row = outstanding[0]
        return result('COMPLETE_FIELD_EVIDENCE', row.get('action'), row,
                      'Keep numerical screening within the modeled reach, flows and sampled locations. Obtain the missing survey accuracy or comparable independent observations before claiming field validation.',
                      '数值初筛限于已计算河段、流量及已核验测点。补齐测量精度或可比的独立观测后，再评价现场验证结果。')
    if outstanding:
        row = next((r for r in outstanding if r['state']=='exceeded'), outstanding[0])
        return result('RESOLVE_CRITERION', row.get('action'), row,
                      'Recheck this criterion after its source or hydraulic input changes.',
                      '该项的来源或水力输入有变化后，再核验这条用途条件。')
    if steps:
        row = steps[0]
        return result('CHECK_LOCAL_EVIDENCE', row.get('action'), row,
                      'Keep interpretation within the tested event and reach.',
                      '本次解释限定在已核验的事件和河段内。')
    if decision.get('state')=='CONDITIONS_MET':
        return result('REVIEW_SCOPED_USE', dict(tool='qa'), decision,
                      'Review native warnings, the modeled flows and independent observation coverage before transfer. Apply only to the stated scope.',
                      '交接前核对原生警告、本版流量和独立测点覆盖，仅在登记的范围内采用。')
    return result('REGISTER_CRITERIA', dict(tool='revision'), decision,
                  'Register intended use and evidence requirements before selecting an edition.',
                  '先登记用途及证据要求，再选用交付版本。')
