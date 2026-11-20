'use strict';
function renderWarningStudy(parent){
 const actions={extent_bend:tr('Extend ends along terrain','按地形延伸外端'),extent_straight:tr('Straight extensions','沿原轴延伸'),joint_overbank:tr('Coordinate overbank directions','联合调整漫滩方向'),infill_upstream:tr('Add upstream sections','上侧加密'),infill_downstream:tr('Add downstream sections','下侧加密')};
 const box=details(parent,'Reduce native HEC-RAS warnings','自动处理 HEC-RAS 原生警告');
 box.id='qa-tool-warning-study';
 box.append(el('p',tr('Compare terrain-based alternatives at the saved flows and boundaries. Each trial uses HEC-RAS. The original stays available.','使用已保存的流量和边界条件，对比从 DEM 推导的几何方案。每轮调用 HEC-RAS，原项目可随时查看。')));
 const pending=current.pending_study_plan?.analysis_kind==='native_warning_review'?current.pending_study_plan:null;
 const rounds=field(box,'warning-rounds','Maximum calculations','最多计算轮数',pending?.policy.maximum_rounds??8,'number');
 rounds.min=1;rounds.max=12;rounds.step=1;
 const width=field(box,'warning-width','Maximum extended width (ft)','延伸后允许的断面总宽（ft）',pending?.policy.maximum_width_ft??2000,'number');
 width.min=120;width.max=2000;
 const preview=el('div');
 function show(plan,token){
  preview.replaceChildren();
  const m=plan.policy.metrics;
  preview.append(el('p',tr('Baseline native warnings / notes / errors: ','基准原生警告／备注／错误：')+[m.warnings,m.notes,m.errors].join(' / ')+tr(' · wet ends: ',' · 湿端：')+m.wet_ends),
   el('p',tr('Tries a 0.30 ft endpoint margin, coordinated DEM-only overbank directions and DEM midpoints near numerical warnings. It retains the original channel samples, bank positions and roughness. Divided flow and physical controls remain for engineering review.','试算按 0.30 ft 余高延伸端点，尝试相邻 DEM 漫滩断面方向的协同调整，并在数值警告附近测试新增断面。保留原主槽采样、岸站位置和糙率，分流与实际水力控制留待工程判断。')),
   button('Confirm limits and start automatic review','确认范围并自动试算',async()=>{
    await api('study-start',{id:current.id,revision:current.revision,token,confirmed:true});await open(current.id);
   },'primary'));
 }
 const prepare=button('Preview scope and original warnings','查看试算范围和原始警告',async()=>{
  const p=await api('study-prepare',{id:current.id,revision:current.revision,kind:'warning_review',maximum_rounds:Number(rounds.value),maximum_width_ft:Number(width.value)});
  current.pending_study=p.entry;current.pending_study_plan=p.plan;show(p.plan,p.token);
  notify(tr('Scope ready. Confirm to run the displayed batch.','范围已准备好，确认后开始此批次。'));
 });
 box.append(prepare,preview);
 for(const input of [rounds,width])input.addEventListener('input',()=>preview.replaceChildren());
 if(pending)show(pending,current.pending_study.sha256);
 const result=current.warning_study;if(!result)return;
 const reasons={BUDGET_REACHED:tr('Calculation limit reached','已达到计算轮数上限'),NO_MORE_DISTINCT_ELIGIBLE_GEOMETRIES:tr('No further eligible terrain change','可行地形修订已用完'),ZERO_WARNINGS_AND_CLEAR_ENDS:tr('Zero warnings and ends above the trial margin','警告为零且端点满足试算余高'),NATIVE_ERROR_REVIEW:tr('Native error requires review','原生错误待处理'),COMPUTATION_INCOMPLETE:tr('Calculation incomplete','计算未完成'),NATIVE_EVIDENCE_INCOMPLETE:tr('Native evidence incomplete','原生证据不完整')};
 const label=id=>id==='baseline'?tr('Original','基准'):id;
 box.append(el('p',(reasons[result.stop]||result.stop)+tr(' · Lowest warning count: ',' · 警告数最低：')+label(result.lowest_count)+tr(' · Suggested for review: ',' · 建议复核：')+label(result.recommended)));
 table(box,[tr('Case','工况'),tr('Sections','断面'),tr('Warnings / notes / errors','警告／备注／错误'),tr('Critical / numerical warnings','临界回退类／数值突变'),tr('Wet ends','湿端'),tr('Minimum end margin (ft)','最小端点余高（ft）'),tr('Max |Δ WSE| (ft)','最大水位差（ft）')],result.cases.map(c=>{
  const m=c.metrics;return [label(c.id),m.section_count,[m.warnings,m.notes,m.errors].join(' / '),[m.critical,m.numerical].join(' / '),m.wet_ends,m.min_margin_ft.toFixed(3),m.max_wse_delta_ft.toFixed(3)];
 }));
 const select=field(box,'warning-case','Inspect case','查看工况',result.recommended,'select',result.cases.map(c=>[c.id,label(c.id),label(c.id)]));
 const links=el('div');box.append(links);
 function inspect(){
  links.replaceChildren();const c=result.cases.find(c=>c.id===select.value);if(!c)return;
  const step=result.attempts?.find(a=>a.id===c.id);
  if(step)links.append(el('p',label(step.parent)+' → '+(actions[step.action]||step.action)));
  if(c.metrics.delta_at)links.append(el('p',tr('Largest original-station change: ','原断面最大水位变化：')+c.metrics.delta_at[0]+' · RS '+c.metrics.delta_at[1]+' · '+c.metrics.signed_delta_ft.toFixed(4)+' ft'));
  if(c.native_file){const raw=el('a',tr('Open original HEC-RAS messages','查看 HEC-RAS 原生警告原文'));raw.href='file/'+c.native_file.path;links.append(raw);}
  const download=el('a',tr('Open calculation evidence (JSON)','查看计算证据（JSON）'));download.href='file/'+c.audit.path;links.append(download);
  links.append(button('Open HEC-RAS project folder','打开 HEC-RAS 工程目录',async()=>{await api('open-folder',{id:current.id,path:c.project.path.slice(0,c.project.path.lastIndexOf('/'))});}));
  if(c.id!=='baseline')links.append(button('Create editable revision from this trial','用此工况创建独立可编辑修订版',async()=>{await continueStudyCase('warning_review',c.id,current.latest_warning_study.sha256);}));
 }
 select.addEventListener('change',inspect);inspect();
 if(result.path_counts?.locations){
  const p=result.path_counts;
  if(p.intervals){
   box.append(el('p',tr('Secondary wet intervals with a DEM route in the 100 m screen: ','100 m 范围内找到地表连通路径的次级湿区：')+p.connected+' / '+p.intervals+tr(' · Complete search windows: ',' · DEM 完整覆盖的搜索窗口：')+p.complete+' / '+p.intervals+tr('. Discharge needs independent evidence.','。实际过流量仍需其他证据。')));
  }else{
   box.append(el('p',tr('Terrain connectivity could not be evaluated for these warnings. Inspect the DEM and cross sections.','本次地形筛查无法判定这些分流警告的连通性，请核对 DEM 和断面。')));
  }
 }
 if(result.divided_paths){const paths=el('a',tr('Open DEM connectivity screen for remaining divided flow','查看剩余分流区的 DEM 连通性筛查'));paths.href='file/'+result.divided_paths.path;box.append(paths);}
 const remaining=details(box,'Remaining native messages in suggested case','推荐工况剩余原生信息');
 table(remaining,['RS',tr('Profile','工况'),tr('Severity','级别'),tr('Native text','原生原文')],result.residual.map(r=>[r.station,r.profile,r.severity,r.text]));
 if(result.residual.length)remaining.append(el('p',tr('For divided flow, trace the overbank connections and road openings. For critical-depth fallbacks, check local bed controls, flow regime and boundaries.','出现分流时核对漫滩连通性与道路开口；出现临界水深回退时核对局部河床控制、流态与边界。')));
}
