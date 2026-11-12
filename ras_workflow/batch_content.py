"""Full batch reports in either language, with a separate executive scope."""
from .common import ROOT
from .report import document, table, fmt
from .report_navigation import finish
from docx.shared import Inches


def build(data, source, language='en', detail='full'):
    cn=language=='zh-CN'; full=detail=='full'; tr=lambda en,zh:zh if cn else en
    d=document(tr('Batch Hydraulic Review Report' if full else 'Batch Executive Summary','批量水力复核报告' if full else '批量执行摘要'))
    d.core_properties.language='zh-CN' if cn else 'en-US'
    d.add_paragraph(data['queue_id']+' | UTC '+data['created_utc'][:19],'Subtitle')
    d.add_paragraph(tr('This report retains the latest attempt for each job, including failed and pending jobs. Report generation does not start a solver. Inputs, hydraulic QA and engineering acceptance are assessed separately.','本报告保留每项任务的最后一次尝试，包括失败及等待任务。生成报告不调用求解器；输入、水力 QA 和工程接受分别判断。'))
    table(d,[tr('Job','任务'),tr('Queue','队列'),tr('Calculation','计算')],[[j['job_id'],j['queue_status'],j['calculation_status']] for j in data['jobs']],[2.7,1.8,2.2])
    d.add_paragraph(tr('Engineering acceptance: NOT_ASSESSED. Different sites and vertical datums cannot be compared by absolute water elevation or combined into a site-safety conclusion.','工程接受：NOT_ASSESSED。不同场地或高程基准的绝对水位不能直接比较，也不能汇总成场地安全结论。'))
    for job in data['jobs']:
        if full:d.add_page_break()
        d.add_heading(job.get('title',job['job_id']),1)
        d.add_paragraph(tr('Input category: ','输入类别：')+str(job.get('case_kind')))
        d.add_paragraph(tr('Job / latest state / attempts: ','任务 / 最新状态 / 尝试次数：')+job['job_id']+' / '+job['queue_status']+' / '+str(job['attempt_count']))
        hyd=job['hydraulics']
        if hyd:
            d.add_paragraph(tr('Verified reused solver output: ' if job['solver_reused'] else 'Native run for the cited attempt: ','核验后复用的求解输出：' if job['solver_reused'] else '所引尝试的原生运行：')+hyd['run_id'])
            table(d,['Profile','Q cfs','HW ft','TW ft'],[[p['profile_id'],fmt(p['flow_cfs']),fmt(p['metrics']['headwater_wse_ft']),fmt(p['metrics']['tailwater_wse_ft'])] for p in hyd['profiles']],[1.5,1.5,1.85,1.85])
            d.add_paragraph(tr('Datum: ','高程基准：')+str(hyd['datum'])+'; international ft. '+tr('Hydraulic QA: ','水力 QA：')+hyd.get('hydraulic_qa_status','REVIEW_REQUIRED'))
            if full:
                d.add_paragraph('HW / TW RS: '+', '.join(p['headwater_rs']+' / '+p['tailwater_rs'] for p in hyd['profiles']))
                d.add_picture(str(ROOT/job['profile_plot']['image']['path']),width=Inches(6.5))
                d.add_paragraph(tr('Figure: native section results in upstream-to-downstream order, not a distance axis or continuous culvert water surface.','图：原生断面结果按上游至下游排序，横轴不是距离，也不表示涵内连续水面。'),'Caption')
                d.add_paragraph(tr('Diagnostic counts: ','诊断计数：')+str(hyd.get('diagnostic_counts',{})))
                d.add_paragraph(tr('Review complete native warnings and conditional inputs for each run. Reference cases do not establish field calibration.','逐运行复核完整原生警告和条件性输入；参考案例不构成现场校准。'))
        else:
            d.add_paragraph(tr('Site computation is incomplete. Water levels, culvert velocities and roadway flow remain unavailable.','本站计算尚未完成，水位、涵内流速及道路流量仍未取得。'))
            for gap in job.get('gate',{}).get('blocking_items',[])+job['errors']:d.add_paragraph(str(gap))
        if job.get('summary'):d.add_paragraph('Summary SHA-256: '+job['summary']['sha256'])
        if full:
            m=job['map']
            if m.get('image'):
                d.add_page_break();d.add_heading(tr('Terrain and model layout','地形与模型布局')+' — '+job['job_id'],1)
                d.add_picture(str(ROOT/m['image']['path']),width=Inches(6.5))
                d.add_paragraph(tr('Figure: bound terrain/input snapshots, not an inundation map. Scale in metres; axes retain the source CRS units.','图：绑定的地形及输入快照，不是淹没图。比例尺为米，坐标轴保留原坐标系单位。'),'Caption')
                d.add_paragraph(str(m['vertical_unit'])+' / '+str(m['vertical_datum'])+'; DEM SHA-256: '+m['raster']['sha256'])
            else:d.add_paragraph(tr('Location map unavailable: ','位置地图未取得：')+m.get('reason',m['status']))
    d.add_paragraph('batch_data.json SHA-256: '+source['sha256'])
    return finish(d,cn,full)
