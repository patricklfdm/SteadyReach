"""Small terminal entry for users who do not know the configuration schema."""
import json
from .common import ROOT, rel, read, safe_path, save


def ask(en, zh, choices=None):
    while True:
        value=input(en+' / '+zh+': ').strip()
        if value and (choices is None or value in choices):return value
        print('Please enter a value'+(' ('+', '.join(choices)+')' if choices else '')+' / 请填写有效值')


def native_import(source=None, output=None, prepare_only=False, review_path=None, browser=False, open_browser=True):
    from . import native_review
    if review_path:path=safe_path(ROOT,review_path)
    else:
        if not source or not output:raise ValueError('Supply --source and a new --output folder, or --review to resume')
        path=native_review.prepare(source,output)
    packet=read(path)
    print('Selected plan / 所选计划: '+packet['selected_plan']+' | '+packet['regime'])
    print('Reach / 河段: '+packet['river_reach']+' | XS / 断面: '+str(len(packet['sections'])))
    for p in packet['profiles']:print('  '+p['id']+': '+str(p['flow_cfs'])+' cfs')
    for b in packet['expected_native']['groups']:
        print('  '+b['name']+': '+str(b['count'])+' × '+b['shape']+'; span/rise '+str(b['span_ft'])+'/'+str(b['rise_ft'])+' ft; length '+str(b['length_ft'])+' ft; inverts '+str(b['us_invert_ft'])+'/'+str(b['ds_invert_ft'])+' ft')
    for side in ['upstream','downstream']:
        values=list(dict.fromkeys(json.dumps(b[side],sort_keys=True) for b in packet['boundaries']))
        print('  '+side+' boundary / 边界: '+'; '.join(values))
    ns=sorted({row[1] for section in packet['sections'] for row in section['manning']})
    print('  Native Manning n values / 原生糙率值: '+', '.join(map(str,ns)))
    print('  Ineffective-area sections / 保留非有效流区断面: '+', '.join(packet['preserved_features']['ineffective_area_sections']))
    print('  Different upstream/downstream road profiles / 上下游不同路顶剖面: '+str(packet['preserved_features']['distinct_road_profiles']))
    print('Review saved / 导入预览已保存: '+rel(path))
    if prepare_only:
        print('.\\.venv\\Scripts\\python.exe workflow.py native-import --review "'+rel(path)+'"')
        return None
    if browser:
        from .native_import_ui import serve
        project=serve(path,open_browser)
        print('Resume / 继续审核: .\\.venv\\Scripts\\python.exe workflow.py native-import --review "'+rel(path)+'" --browser' if project is None else 'Ready / 输入准备完成: '+rel(project))
        if project:print('.\\.venv\\Scripts\\python.exe workflow.py run --project "'+rel(project)+'" --scenario baseline --review')
        return project
    print('Only the selected steady inputs are copied; original files remain unchanged. Review units, datum and source applicability.\n仅复制所选恒定流输入；原件保持不变。请审核单位、基准及来源适用性。')
    if ask('Continue with review? y / n (save and exit)', '继续审核？y / n（保存退出）',['y','n'])=='n':return None
    decision=dict(project_id=ask('Project identifier (letters/numbers/underscore)','项目代号（英文/数字/下划线）'),
        title=ask('Project title','项目标题'),source=ask('Source / version / applicable site','来源、版本及适用地点'),
        reviewer=ask('Reviewer name','审核人姓名'),vertical_datum=ask('Verified vertical datum','已核实的高程基准'))
    unit=ask('Foot convention: 1 international ft; 2 US survey foot','英尺定义：1 国际英尺；2 美国测量英尺',['1','2'])
    decision['native_length_unit']='international ft' if unit=='1' else 'US survey foot'
    print(json.dumps(decision,ensure_ascii=False,indent=2))
    decision['approve']=ask('Approve this conditional input copy? y / n','批准这份条件性输入副本？y / n',['y','n'])=='y'
    save(path.parent/'decision.json',decision)
    if not decision['approve']:return None
    project=native_review.approve(path,decision)
    print('Ready / 输入准备完成: '+rel(project))
    print('.\\.venv\\Scripts\\python.exe workflow.py run --project "'+rel(project)+'" --scenario baseline --review')
    return project


def start(terminal=False,no_browser=False):
    if terminal:return terminal_start()
    from .launcher import serve
    return serve(not no_browser)


def terminal_start():
    print('SteadyReach / 使用入口\n1. New coordinates → DEM and input wizard / 新坐标 → DEM 与填报向导\n2. Existing HEC-RAS steady project / 已有 HEC-RAS 恒定流工程\n3. Public Phelps example / 公开 Phelps 示例\n4. Resume a workflow project.json / 继续已有工作流项目\n0. Exit / 退出')
    choice=ask('Choose','请选择',['0','1','2','3','4'])
    if choice=='0':return 0
    from .cli import run_with_intake
    if choice=='1':
        from .inputs import template
        site=ask('New project identifier','新项目代号');lat=float(ask('WGS84 latitude','WGS84 纬度'));lon=float(ask('WGS84 longitude','WGS84 经度'))
        config=template(site,lat,lon);project=safe_path(ROOT,'projects/'+site+'/project.json')
        if project.parent.exists():raise ValueError('Project folder already exists; choose Resume / 项目目录已存在，请选择继续项目')
        save(project,config);scenario='q100'
    elif choice=='2':
        project=native_import(ask('Path to source .prj','原始 .prj 文件路径').strip('"'),ask('New output folder within this repository','本仓库内的新输出目录'),browser=True)
        if project is None:return 3
        scenario='baseline'
    elif choice=='3':
        from .public_case import prepare
        output=ask('New example folder, e.g. projects/phelps_first','新示例目录，例如 projects/phelps_first')
        project=prepare('benchmarks/phelps_brook/recipe.json',output,True);scenario='baseline'
        print('Official input replication; not a surveyed validation of a new design. / 公开模型复算，不等于新设计实测验证。')
    else:
        from .inputs import load
        project,config=load(ask('Path to workflow project.json','工作流 project.json 路径').strip('"'))
        ids=[v['id'] for v in config['scenarios']];scenario=ids[0] if len(ids)==1 else ask('Scenario','工况',ids)
    print('Project / 项目: '+rel(project))
    if ask('Run HEC-RAS or open the missing-input wizard now? y / n','现在运行 HEC-RAS 或打开缺失输入向导？y / n',['y','n'])=='n':return 3
    code=run_with_intake(project,scenario,interactive=True)
    if code in (0,3):
        if choice=='3' and code==0:
            from .public_case import compare
            from .report import generate
            from .common import unique_id
            state=read(project.parent/'state.json');summary=ROOT/state['latest_summary']['path'];out=project.parent/'reference_reports'/unique_id()
            comparison=out/'comparison.json';result=compare('benchmarks/phelps_brook/recipe.json',summary,comparison)
            generate(summary,out/'reports',comparisons=[comparison]);print('Published reference / 公开参考对比: '+result['status'])
        from .project_home import prepare
        from .review_server import serve
        home=prepare(project);serve(project,home.get('qa_session'),True)
    return code
