"""Evidence-based next actions; organizing work never changes or accepts a model."""
from collections import Counter

from .common import ROOT, intact, read


WET = {'WET_SECTION_EDGE', 'NATIVE_WET_SECTION_EDGE'}
NATIVE_GAPS = {'NATIVE_WARNING_TABLE_INCOMPLETE', 'CULVERT_GROUP_DETAIL_NOT_EXTRACTED'}
SPACING = {'MINIMUM_ERROR_SOLUTION', 'CRITICAL_DEPTH_FALLBACK', 'ENERGY_BALANCE_ERROR',
           'NATIVE_ENERGY_NOT_BALANCED', 'NATIVE_CRITICAL_DEPTH_FALLBACK',
           'NATIVE_CONVEYANCE_CHANGE', 'NATIVE_LARGE_ENERGY_LOSS', 'NATIVE_VELOCITY_HEAD_CHANGE'}
PATHS = {'NATIVE_DIVIDED_FLOW', 'NATIVE_MULTIPLE_CRITICAL_DEPTH', 'NATIVE_HYDRAULIC_JUMP',
         'DOWNSTREAM_EGL_RISE', 'NATIVE_SUPERCRITICAL_START'}
BALANCE = {'RIVER_DISCHARGE_MISMATCH', 'STRUCTURE_FLOW_IMBALANCE', 'FLOW_SPLIT_NOT_FULLY_OBSERVED',
           'NATIVE_DISPLAY_MACHINE_DIFFERENCE'}


def text(en, zh):
    return dict(en=en, zh=zh)


def organize(model, summary, diagnostics, studies, evidence_errors=()):
    """Pure decision rules over verified inputs; priorities are work order, not risk scores."""
    issues = diagnostics.get('issues', []) if diagnostics else []
    actions = []
    assigned = set()

    def add(key, target, title, explanation, rows=(), mode='REVIEW', **extra):
        rows = list(rows)
        assigned.update(i['id'] for i in rows)
        actions.append(dict(id=key, target=target, title=title, explanation=explanation, mode=mode,
            issue_ids=[i['id'] for i in rows], issue_records=[{k:i.get(k) for k in ('id','code','profile','station')} for i in rows], records=len(rows),
            codes=dict(Counter(i['code'] for i in rows)),
            locations=sorted({(str(i.get('profile') or ''), str(i.get('station') or '')) for i in rows}), **extra))

    def matching(codes):
        return [i for i in issues if i['code'] in codes]

    workflow = not model.get('native_review')
    river = model.get('model_type') == 'river'
    if evidence_errors:
        add('evidence', 'qa', text('Resolve changed or unavailable evidence first', '先处理已改变或不可用的证据'),
            text('Some completed studies could not be authenticated. Their apparent success does not suppress any action below.',
                 '部分试算无法核验，不能用其表面完成状态省略下方检查。'), errors=list(evidence_errors))
    if not diagnostics or matching(NATIVE_GAPS) or diagnostics.get('warning_coverage') not in (
            'ALL_COMPUTED_PROFILES_VERIFIED_SINGLE_REACH', 'ALL_REQUESTED_PROFILES_USER_CONFIRMED', 'EXPORTED_SCOPE_OPERATOR_ATTESTED'):
        add('native', 'native', text('Complete the native evidence', '补齐原生结果证据'),
            text('Retry the native table export without solving. Inspect any remaining flow or display discrepancies separately.',
                 '无需重算即可重试原生表导出；剩余流量或显示差异需另行判断。'), matching(NATIVE_GAPS), mode='AUTOMATED_EXPORT')
    if matching(BALANCE):
        add('balance', 'qa', text('Check flow and output consistency', '核对流量及输出一致性'),
            text('Inspect the listed native and machine values before interpreting geometry changes; blank outputs are not zero.',
                 '解释几何修改前先核对所列原生值和机器值；空白输出不等于零。'), matching(BALANCE))

    sensitivity = []
    coverage = []
    spacing = []
    for study in studies:
        if study.get('coverage'):
            coverage.append(study['coverage'])
        elif study.get('convergence'):
            spacing.append(study)
        else:
            changes = {c['id']: c.get('changes', []) for c in study['cases']}
            for comparison in study['comparisons']:
                path = next((r['path'] for r in changes[comparison['case']] if r['path'] != 'blockage_basis'), None)
                maximum = max((r['max_matched_xs_delta_wse_ft'] for r in comparison['rows']), default=None)
                if path and maximum is not None:
                    sensitivity.append(dict(parameter=path, case=comparison['case'], max_delta_ft=maximum,
                                            analysis=study['analysis']))
    boundary_tested = [r for r in sensitivity if r['parameter'].startswith(('boundary_slopes.', 'boundaries.'))]
    if workflow:
        add('boundary', 'sensitivity', text('Review tested boundary response' if boundary_tested else 'Check boundary assumptions and ranges',
                                         '复核已测试的边界响应' if boundary_tested else '核对边界假设及可用范围'),
            text('Use the sealed-source range tool and inspect its applicability. A small response does not establish a correct boundary; do not select a slope because it removes warnings.',
                 '使用有来源的范围整理工具并判断其适用性。响应小不代表边界正确，不应因某坡降警告少就采用。'),
            mode='REVIEW_TESTED_RANGE' if boundary_tested else 'PREVIEW_THEN_CONFIRM', tested=boundary_tested)
    wet = matching(WET)
    if wet:
        if coverage:
            last = coverage[-1]
            add('coverage', 'coverage', text('Review the existing repair batch before repeating it', '先查看已有湿端修订批次，避免重复计算'),
                text('These warnings belong to the displayed baseline. The completed repair is a separate calculation: inspect its final report and continue from that case when appropriate.',
                     '这些警告属于当前显示的基准；已有修订结果是独立计算，请查看最终报告，必要时从该工况继续。'), wet,
                mode='REVIEW_COMPLETED_BATCH', outcome=last['status'])
        else:
            add('coverage', 'coverage' if workflow and river else 'revision',
                text('Preview section coverage repair', '预览断面覆盖修正'),
                text('Check actual floodplain connectivity, then review bounded DEM extensions. Existing bank positions and interior samples are preserved by the wet-end batch. Confirmation is required before calculation.',
                     '先判断实际漫滩连通性，再核对有限范围 DEM 延伸。湿端批次保留岸站平面位置及内部样点，确认后才计算。'), wet,
                mode='PREVIEW_THEN_CONFIRM' if workflow else 'NATIVE_EDITOR')
    if matching(PATHS):
        add('paths', 'atlas', text('Inspect flow paths and transitions', '核对过流路径与流态转换'),
            text('Review banks, disconnected wet areas, controls and actual bypass paths. Terrain alone cannot decide whether an area conveys flow; no ineffective area or bank relocation is applied here.',
                 '核对岸站、分隔湿区、控制条件及实际绕流路径。地形本身不能决定区域是否有效过流；此处不会自动设置非有效流区或移动岸站。'), matching(PATHS))
    if workflow and river:
        status = spacing[-1]['convergence']['status'] if spacing else 'NOT_TESTED_FOR_THIS_BASELINE'
        excluded = spacing[-1].get('excluded_intervals', []) if spacing else []
        add('spacing', 'spacing', text('Review the existing spacing comparison' if spacing else 'Preview a section-spacing trial',
                                      '复核已有断面加密比较' if spacing else '预览断面加密试算'),
            text('Treat section count and placement as a numerical check. Review coverage first, keep hydraulic inputs fixed, and inspect both consecutive refinements. Changed geometry needs a new comparison.',
                 '断面数量及布置需要数值检验。先复核覆盖，保持水力输入一致，检查连续两级加密；几何改变后需要新的比较。'), matching(SPACING),
            mode='REVIEW_COMPLETED_BATCH' if spacing else 'PREVIEW_THEN_CONFIRM', outcome=status,
            excluded_intervals=excluded)
    elif matching(SPACING):
        add('spacing', 'revision', text('Review local geometry and energy solution', '复核局部几何与能量解'),
            text('Automatic river-spacing trials do not support this model type. Inspect the listed locations and prepare an appropriate independent geometry revision.',
                 '此模型类型不适用自动纯河道加密，请核对所列位置并准备适当的独立几何修订。'), matching(SPACING))
    unassigned = [i for i in issues if i['id'] not in assigned]
    if unassigned:
        add('other', 'qa', text('Read the remaining native messages', '阅读其余原生信息'),
            text('No automatic remedy has been assigned to these messages. Inspect each in its native context; none is discarded or marked resolved.',
                 '这些信息尚无自动处置规则，请结合原生上下文逐项阅读；不会丢弃或标记已解决。'), unassigned)
    add('inputs', 'revision', text('Confirm physical data and assumptions', '核实实物资料与假设'),
        text('Check datum, submerged bed, reach limits, banks, structure details and boundary applicability where relevant. Successful calculation and dry section ends do not supply missing observations.',
             '按项目实际情况核对高程基准、水下河床、河段边界、岸站、结构资料及边界适用性。计算成功和断面端点干燥不能补足实测资料。'))
    delivery = model.get('delivery') or model.get('latest_delivery') or {}
    if model.get('exports_need_refresh') or delivery.get('status') != 'READY_FOR_REVIEW':
        add('delivery', 'delivery', text('Update or recover reports and both packages', '更新或恢复报告及双交付包'),
            text('Reuse the saved calculation. Complete study comparisons enter the refreshed report; failed exports can be retried without solving.',
                 '复用已保存计算，将已完成的试算比较纳入更新报告；导出失败可单独重试。'), mode='AUTOMATED_EXPORT')
    else:
        add('delivery', 'delivery', text('Inspect the current delivery', '检查当前交付文件'),
            text('Check report interpretation, map alignment and readable layouts. Package readiness is not engineering acceptance.',
                 '核对报告解释、地图对齐与版面可读性。交付包就绪不代表工程接受。'), mode='VISUAL_REVIEW')
    return dict(status='GUIDANCE_NOT_ACCEPTANCE', run_id=summary['hydraulics']['run_id'], actions=actions,
        issue_count=len(issues) if diagnostics else None, assigned_issue_count=len(assigned), warnings_resolved=0,
        verified_study_count=len(studies), source_errors=list(evidence_errors),
        solver_started=False, geometry_changed=False, engineering_acceptance='NOT_ASSESSED')


def load_evidence(key, body):
    from . import app_core as core
    from .qa_review import load_summary
    m = core.model(key)
    core.require_idle(m)
    if body.get('summary_hash') != m.get('summary', {}).get('sha256') or not intact([m.get('summary', {})]):
        raise ValueError('The displayed calculation changed; reopen results')
    path, summary, hyd = load_summary(ROOT/m['summary']['path'])
    diagnostics = None
    errors = []
    if hyd.get('diagnostics') and intact([hyd['diagnostics']]):
        diagnostics = read(ROOT/hyd['diagnostics']['path'])
        if diagnostics.get('run_id') != hyd['run_id'] or not intact(diagnostics['sources']):
            diagnostics = None
            errors.append('Diagnostic sources changed; regenerate evidence before relying on the action list.')
    if summary.get('native_supplement') and diagnostics:
        from .app_outputs import validate, diagnostics as supplement_diagnostics
        diagnostics = supplement_diagnostics(hyd, validate(summary['native_supplement']))
    return m, path, summary, hyd, diagnostics, errors


def collect(key, body):
    from .report_studies import collect as collect_studies
    m, path, summary, hyd, diagnostics, errors = load_evidence(key, body)
    try:
        studies, sources = collect_studies(path, summary)
    except (ValueError, OSError, KeyError) as error:
        studies, sources = [], []
        errors.append(str(error))
    for field in ('latest_study', 'latest_spacing', 'latest_coverage'):
        entry = m.get(field)
        if not entry:
            continue
        if not intact([entry]):
            errors.append(field + ': saved analysis changed or is missing.')
            continue
        analysis = read(ROOT/entry['path'])
        if analysis.get('status') == 'INCOMPLETE' or analysis.get('failed_cases'):
            errors.append(field + ': earlier batch has incomplete cases; it does not establish a completed comparison.')
    result = organize(m, summary, diagnostics, studies, errors)
    from .app_core import folder
    from .operator_log import inventory,lineage
    result['operator_actions'] = inventory(folder(key))
    result['operator_lineage'] = lineage(m)
    if m.get('model_type')=='river':
        from .river_review import local_problems,response
        from .revision_inputs import bound_inputs
        try:
            _,geometry,geometry_sources = bound_inputs(summary)
            sources += geometry_sources
            result['local_problems'] = local_problems(result['actions'],[r['rs'] for r in geometry['cross_sections']])
        except (ValueError,KeyError,OSError) as error:
            result['source_errors'].append(str(error))
        result['parameter_response']=response(studies)
    result.update(summary=m['summary'], sources=[m['summary']]+sources)
    return result
