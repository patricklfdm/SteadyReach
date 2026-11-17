"""Reports consume exactly one hashed job summary; never a global site result."""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from .common import *

def document(title):
    d=Document();sec=d.sections[0];sec.page_height=Inches(11.69);sec.page_width=Inches(8.27)
    sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.72)
    for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Caption']:
        s=d.styles[name];s.font.name='Calibri';s.font.color.rgb=RGBColor(0,0,0)
        s._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
    for s in d.styles:
        for b in list(s._element.iter(qn('w:pBdr'))):b.getparent().remove(b)
    d.styles['Normal'].font.size=Pt(10);d.styles['Normal'].paragraph_format.space_after=Pt(6)
    d.styles['Normal'].paragraph_format.line_spacing=1.1;d.styles['Title'].font.size=Pt(21)
    d.styles['Heading 1'].font.size=Pt(14);d.add_paragraph(title,'Title')
    f=sec.footer.paragraphs[0];f.add_run('SteadyReach | ')
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');f._p.append(field)
    return d

def table(d,headers,rows,widths):
    t=d.add_table(rows=1,cols=len(headers));t.autofit=False
    for i,w in enumerate(widths):
        t.columns[i].width=Inches(w);t._tbl.tblGrid.gridCol_lst[i].set(qn('w:w'),str(Inches(w).twips))
    for c,v in zip(t.rows[0].cells,headers):c.text=str(v)
    for row in rows:
        for c,v in zip(t.add_row().cells,row):c.text=str(v)
    for n,row in enumerate(t.rows):
        pr=row._tr.get_or_add_trPr()
        if n==0:pr.append(OxmlElement('w:tblHeader'))
        pr.append(OxmlElement('w:cantSplit'))
        for i,cell in enumerate(row.cells):
            cell.width=Inches(widths[i]);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E1E8F0' if n==0 else ('F4F6F8' if n%2 else 'FFFFFF'));cell._tc.get_or_add_tcPr().append(shade)
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc=cell._tc.get_or_add_tcPr();borders=OxmlElement('w:tcBorders')
            for side in ['top','bottom','left','right']:
                edge=OxmlElement('w:'+side);edge.set(qn('w:val'),'single');edge.set(qn('w:sz'),'4');edge.set(qn('w:color'),'D9D9D9');borders.append(edge)
            tc.append(borders);margins=OxmlElement('w:tcMar')
            for side in ['top','bottom','left','right']:
                v=OxmlElement('w:'+side);v.set(qn('w:w'),'75');v.set(qn('w:type'),'dxa');margins.append(v)
            tc.append(margins)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(3)
                # Keep a short table together; long schedules repeat their header.
                if len(t.rows)<=7 and n<len(t.rows)-1:p.paragraph_format.keep_with_next=True
                if n==0:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:r.font.size=Pt(9);r.bold=n==0
    d.add_paragraph()

def fmt(v):return 'null' if v is None else f'{v:.3f}'

def render(docpath):
    from .report_tools import render as portable_render
    return portable_render(docpath)

def detail_appendix(doc, bundle, chinese):
    doc.add_page_break()
    doc.add_heading('原生孔组详细表补充' if chinese else 'Native group detail supplement',1)
    doc.add_paragraph('这是同一历史求解的追加抽取，本次没有重新求解。数据来自实际观察并导出的原生 Culvert Output 表，分辨率为 0.01；空白保持 null，原始 COM 全精度结果未被覆盖。输入、警告和工程接受状态不变。' if chinese else 'Additional extraction from the same existing solve; no new solver run. Values come from observed native Culvert Output exports at 0.01 display resolution. Blanks remain null; original full-precision COM values are preserved. Input, warning and engineering acceptance states are unchanged.')
    display=lambda v: 'null' if v is None else f'{v:.2f}'
    table(doc,['Profile','Group','Q cfs','V inlet ft/s','V outlet ft/s','Control'],
          [[r['profile'],r['native_group'],display(r['flow_cfs']),display(r['inlet_velocity_fts']),display(r['outlet_velocity_fts']),r['control'] or 'null'] for r in bundle['rows']],
          [.85,1.05,1.1,1.25,1.25,1.3])
    table(doc,['Profile','Group','E.G. IC ft','E.G. OC ft','Full length ft'],
          [[r['profile'],r['native_group'],display(r['inlet_control_egl_ft']),display(r['outlet_control_egl_ft']),display(r['full_flow_length_ft'])] for r in bundle['rows']],
          [1.0,1.3,1.5,1.5,1.5])
    doc.add_paragraph(('高程基准 / 单位：' if chinese else 'Datum / unit: ')+str(bundle['datum'])+' / '+str(bundle['unit']))
    doc.add_paragraph(('原始运行：' if chinese else 'Original run: ')+bundle['run_id'])
    doc.add_paragraph(('限制：文本自身不含输出哈希，来源对应依赖记录的界面观察。首组已按显示精度与独立 COM 输出交叉核对。该补充不关闭水力 QA，也不代表工程认可。' if chinese else 'The text has no embedded output hash; attribution relies on the recorded UI observation. First-group values were cross-checked against independent COM output at display precision. This supplement does not close hydraulic QA or grant engineering acceptance.'))


def generate(summary_path,folder,culvert_details=None,comparisons=(),context=None):
    if read(summary_path).get('hydraulics'):
        from .report_content import generate as readable
        result=readable(summary_path,folder,culvert_details,comparisons,context)
    else:
        if comparisons or context:raise ValueError('Comparisons and criteria require computed hydraulic results')
        result=generate_incomplete(summary_path,folder,culvert_details)
    from .report_catalog import register
    register(summary_path,safe_path(ROOT,folder)/'report_manifest.json')
    return result


def build_incomplete(s, summary_path, language='en', detail='full'):
    """Report existing preparation and gaps without a hydraulic result table."""
    if s.get('hydraulics'):raise ValueError('Use the verified computed-report builder')
    if language not in ('en','zh-CN') or detail not in ('full','summary'):
        raise ValueError('Unsupported report language or detail')
    cn=language=='zh-CN';full=detail=='full';tr=lambda en,zh:zh if cn else en
    c=s['configuration'];t=s.get('terrain',{});d=document(c['title']+tr(' Workflow Status Report' if full else ' Executive Summary',' 工作流状态报告' if full else ' 执行摘要'))
    d.core_properties.language='zh-CN' if cn else 'en-US'
    d.add_paragraph(tr('Calculation incomplete','计算尚未完成'),'Subtitle')
    d.add_paragraph(tr('Site steady-flow computation is incomplete. This report records available preparation and missing inputs; no hydraulic results are provided.',
        '本站恒定流计算尚未完成。本报告记录已完成的准备工作及缺失输入，不提供水力结果。'))
    status=s.get('workflow_status')
    if status=='WAITING_FOR_INPUT':
        d.add_paragraph(tr('The workflow is waiting for your input or review. Complete the local wizard, save for later, or explicitly cancel. Missing information is not a completed calculation.',
            '工作流正在等待补充或审核输入。可完成本机向导、保存待续或明确放弃；缺资料状态不等于计算完成。'))
    elif status=='CANCELLED':d.add_paragraph(tr('The user cancelled this workflow. Existing files and evidence are preserved.','用户已放弃此工作流；已有文件和证据保留。'))
    table(d,[tr('Assessment','判断层次'),tr('Current status','当前状态')],[
        [tr('Calculation','计算执行'),s['calculation_status']],
        [tr('Input evidence','输入充分性'),s['gate']['input_adequacy_status']],
        [tr('Hydraulic QA','水力 QA'),'NOT_STARTED'],
        [tr('Engineering acceptance','工程接受'),'NOT_ASSESSED']],[1.65,5.15])
    d.add_heading(tr('Missing information and next actions','缺失信息与后续动作'),1)
    for v in dict.fromkeys(s['gate'].get('blocking_items',[])+s.get('errors',[])):d.add_paragraph(str(v))
    if status=='WAITING_FOR_INPUT' and s.get('intake'):
        d.add_paragraph(tr('Resume the input wizard from the workspace root:','在工作区根目录恢复填报：'))
        d.add_paragraph('workflow.py intake --project "'+s['intake']['resume_project']+'" --scenario '+s['intake']['scenario'])
    if full:
        d.add_page_break();d.add_heading(tr('Terrain and preparation evidence','地形与准备工作证据'),1)
        d.add_paragraph(tr('Terrain status: ','地形状态：')+t.get('status','NOT_STARTED'))
        loc=c.get('location',{})
        if loc:d.add_paragraph(tr('Site marker latitude / longitude: ','位置标记纬度 / 经度：')+str(loc.get('latitude'))+' / '+str(loc.get('longitude')))
        if t.get('raster'):
            d.add_paragraph(tr('Recorded raster: ','记录的栅格：')+t['raster']['path'])
            d.add_paragraph('SHA-256: '+t['raster']['sha256'])
        if t.get('valid_fraction') is not None:
            d.add_paragraph(tr('Valid AOI pixels: ','AOI 有效像元比例：')+f"{t['valid_fraction']*100:.2f}%")
        if t.get('download_bytes') is not None:d.add_paragraph(tr('Download bytes: ','下载字节数：')+str(t['download_bytes']))
        for field,en,zh in [('horizontal_crs','Horizontal CRS','平面坐标系'),('vertical_unit','Elevation unit','高程单位'),('vertical_datum','Vertical datum','高程基准')]:
            d.add_paragraph(tr(en,zh)+': '+str(t.get(field) or tr('Unavailable','未取得')))
        for v in t.get('limitations',[]):d.add_paragraph(str(v))
        d.add_paragraph(tr('A surface DEM cannot establish buried culvert dimensions or replace missing site evidence. No hydraulic map or water level is inferred before a verified calculation.',
            '地表 DEM 不能确定埋藏涵洞尺寸或替代缺失现场证据。未完成核验的水力计算前，不推导水位或水力图。'))
    d.add_heading(tr('Traceability and interpretation','来源与适用范围'),1)
    d.add_paragraph(tr('Run or attempt: ','运行或尝试：')+s['attempt_id'])
    d.add_paragraph(tr('Attempt recorded UTC: ','尝试记录时间 UTC：')+s['finished_at_utc'][:19])
    d.add_paragraph(tr('Report generated UTC: ','报告生成时间 UTC：')+utc()[:19])
    d.add_paragraph('Summary SHA-256: '+sha(summary_path))
    d.add_paragraph(tr('Report generation does not invoke HEC-RAS. Conditional inputs remain unverified; software/reference examples do not certify a site. Source descriptions and issue messages retain their original wording.',
        '报告生成不调用 HEC-RAS。条件性输入仍未核实，软件或参考示例不证明场地安全；来源说明和问题信息保留原文。'))
    from .report_navigation import finish
    return finish(d,cn,full)


def generate_incomplete(summary_path,folder,culvert_details=None):
    from .report_content import REPORT_VARIANTS
    summary_path=safe_path(ROOT,summary_path);folder=safe_path(ROOT,folder);s=read(summary_path)
    if culvert_details:raise ValueError('Native culvert details require computed hydraulic results')
    if folder.exists() and any(folder.iterdir()):raise ValueError('Report output must be a new or empty directory')
    folder.mkdir(parents=True,exist_ok=True)
    from . import __version__
    manifest=dict(schema_version='incomplete_reports_2.2',created_utc=utc(),generator_version=__version__,edition=folder.name,summary=item(summary_path,'sole_report_data'),
        visual_review='PENDING_HUMAN_PAGE_REVIEW',reports=[],new_solver_calls_by_report=0)
    for language,detail,name in REPORT_VARIANTS:
        path=folder/(name+'.docx');build_incomplete(s,summary_path,language,detail).save(path)
        pdf,n,pngs=render(path)
        manifest['reports'].append(dict(language=language,detail=detail,docx=item(path),pdf=item(pdf),pages=n,
            rendered_pages=[item(x) for x in pngs],render_evidence=item(path.parent/'qa'/path.stem/'render_manifest.json')))
    save(folder/'report_manifest.json',manifest);return manifest
