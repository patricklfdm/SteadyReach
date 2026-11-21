function renderParentStationReview(parent,comparison,peak){
 const m=current, output=el('div');output.setAttribute('aria-live','polite');
 const body={id:m.id,revision:m.revision,summary_hash:m.summary.sha256,mode:'geometry',
  cases:[{id:comparison.parent.summary.sha256,profile:peak.profile},{id:m.summary.sha256,profile:peak.profile}]};
 parent.append(button('Inspect both native runs at this station','并排核查该站两次原生结果',async()=>{
  const data=await api('extent-review',{...body,preview:true});
  drawExtent(output,data,String(Number(peak.station)));
  output.append(button('Save this comparison for a decision','保存这次对比并记录取舍',async()=>{
   const saved=await api('extent-review',body);current=await api('project/'+m.id);
   drawExtent(output,saved,String(Number(peak.station)));
   notify(tr('Comparison saved. Record your choice below.','对比已保存，可直接在下方记录取舍。'));
  }));
 }),output);
}
function renderExtentReview(parent){
 const box=details(parent,'Compare model editions and mapped flood edges','比较模型版本与历史洪水边线');
 const m=current, key={id:m.id,summary_hash:m.summary.sha256};
 const panel=el('div');box.append(panel);
 box.append(button('Open extent comparison','打开洪水边线对照',async()=>{
  const [data,prior]=await Promise.all([api('extent-options',key),api('extent-current',key)]);
  panel.replaceChildren();
  const choices=data.options.flatMap(o=>o.profiles.map(p=>[o.id+'/'+p,o.label+' · '+p,o.label+' · '+p]));
  const first=field(panel,'extent-first','Base calculation','基准计算',choices.find(v=>v[0].startsWith(data.current+'/'))?.[0],'select',choices);
  const second=field(panel,'extent-second','Second calculation','备选计算','','select',[['','Single calculation','仅基准'],...choices]);
  const mode=field(panel,'extent-mode','Comparison','对照方式','geometry','select',[['geometry','Compare two native runs','对比两次原生计算'],['extent','Include an observed flood edge','加入历史洪水边线']]);
  const form=el('div');panel.append(form);form.hidden=true;mode.onchange=()=>{form.hidden=mode.value!=='extent';};
  const input=field(form,'extent-file','Mapped flood edge','洪水边线文件','','file');input.accept='.geojson,.json,.kml,.kmz';
  const layer=field(form,'extent-layer','KML folder (when multiple layers exist)','KML 文件夹（含多个图层时填写）');
  const event=field(form,'extent-event','Observed event name','观测事件名称'),day=field(form,'extent-date','Event date','事件日期','','date');
  const flow=field(form,'extent-flow','Observed discharge (cfs)','实测事件流量（cfs）','','number');
  const ref=field(form,'extent-reference','Data source / original locator','来源或原件位置');
  const role=field(form,'extent-use','How was this extent used?','本边线的用途','context','select',[
   ['context','Spatial context','空间参照'],['used','Used to select geometry or parameters','曾用于确定几何或参数'],['reserved','Reserved before fitting this model','本模型调参前已留出']]);
  const radius=field(form,'extent-search','Search beyond each end (m)','每端核查距离（m）',400,'number');
  const answer=el('div');panel.append(button('Compare and save','计算并保存对照',async()=>{
   if(mode.value==='extent'&&!input.files.length)throw Error(tr('Select the observed edge file.','请选择观测边线文件。'));
   if(mode.value==='geometry'&&!second.value)throw Error(tr('Choose the second calculation.','请选择第二个计算。'));
   const cases=[first.value,second.value].filter(Boolean).map(v=>{const [id,profile]=v.split('/');return {id,profile};});
   const result=await api('extent-review',{...key,revision:current.revision,cases,mode:mode.value,file:mode.value==='extent'?(await encodeFiles(input.files))[0]:null,
    layer:layer.value,search_m:Number(radius.value),event:{name:event.value,date:day.value,flow_cfs:Number(flow.value),source:ref.value,use:role.value}});
   current=await api('project/'+m.id);drawExtent(answer,result);
   notify(tr('Comparison saved. Update the reports and both packages when ready.','对比已保存，可更新报告和两种交付包。'));
  }));panel.append(answer);if(prior)drawExtent(answer,prior);
 }));
}

function drawExtent(parent,data,focusStation){
 parent.replaceChildren();
 const classes={NATIVE_GEOMETRY_COMPARISON:tr('Comparison of native model editions','原生模型版本对照'),SPATIAL_CONTEXT:tr('Spatial context only: event identity or prior use limits comparison.','空间参照：事件身份或资料用途限制了对比。'),
  USED_FOR_GEOMETRY_OR_CALIBRATION:tr('These edges informed geometry or calibration.','该边线曾用于确定几何或调参。'),
  RESERVED_EVENT_REVIEW:tr('Reserved event matched. Review mapping accuracy and source independence.','已匹配留出事件，仍需复核地图精度与来源独立性。')};
 parent.append(el('p',classes[data.classification],'status'));
 if(data.event)parent.append(el('p',data.event.name+' · '+data.event.date+' · '+data.event.source));
 table(parent,[tr('Calculation','计算'),tr('Profile','工况'),'cfs',tr('Native warnings','原生警告'),tr('Matched XS','匹配断面'),
  tr('Median absolute edge difference, shared XS (m)','共有断面边线绝对差中位数（m）')],data.cases.map(c=>[
   c.label,c.profile,c.flow_cfs,c.native_warning_count,c.matched+' / '+c.total,c.common_median_abs_m]));
 if(data.max_wse_change){const d=data.max_wse_change;parent.append(el('p',tr('Largest common-section WSE change','共有断面最大水位变化')+' '+d.signed_ft.toFixed(3)+' ft @ RS '+d.station));}
 const stations=[...new Set(data.cases.flatMap(c=>c.rows.map(r=>r.rs)))].sort((a,b)=>Number(b)-Number(a));
 const station=field(parent,data.preview?'preview-extent-rs':'extent-rs','Inspect station','核对断面',stations.includes(focusStation)?focusStation:(data.max_wse_change?.station??stations[0]),'select',stations.map(rs=>[rs,'RS '+rs,'RS '+rs]));
 const comparisonToken=data.comparison_token??current.extent_review?.sha256;
 const identity={id:current.id,revision:current.revision,summary_hash:current.summary.sha256,comparison_token:comparisonToken};
 const key=()=>({...identity});
 for(const c of data.cases)for(const issue of c.context_issues||[])parent.append(el('p',c.label+' · '+issue,'warning'));
 const plot=el('div');parent.append(plot);
 function update(){
  plot.replaceChildren();
  const rows=data.cases.map(c=>c.rows.find(r=>r.rs===station.value));
  table(plot,[tr('Calculation','计算'),'WSE (ft)',tr('Left / right shortfall (m)','左／右边线欠覆盖（m）'),tr('Wet ends','湿端'),tr('L/R overbank flow (%)','左右滩地分流（%）'),tr('Warnings at RS','该站警告')],
   rows.map((r,i)=>[data.cases[i].label,r?.wse_ft?.toFixed(3),r?.status==='MATCHED'?[r.left_shortfall_m,r.right_shortfall_m].join(' / '):r?.status,r?.wet_ends,
    r?.left_right_flow_pct?.map(x=>x?.toFixed(1)??'—').join(' / '),r?.native_warnings==null?'—':r.native_warnings.join(', ')||'0']));
  const observed=rows.flatMap((r,i)=>(r?.observations||[]).map(o=>[data.cases[i].label,o]));
  for(const [i,r] of rows.entries()){
   if(r?.section_profile?.station_ft?.length){
    const label=data.cases[i].label;
    atlasSectionPlot(details(plot,label+' · native section (ft)',label+' · 原生断面（ft）'),r.section_profile);
   }
  }
  if(observed.length)table(plot,[tr('Run','计算'),tr('Observation','测量'),tr('Role','用途'),tr('Observed (ft)','实测（ft）'),tr('Residual (ft)','偏差（ft）'),tr('Source / restrictions','来源／限制')],
   observed.map(([label,o])=>[label,[o.date,o.event,o.kind].join(' · '),o.role,o.observed_ft?.toFixed(3),o.residual_ft?.toFixed(3),[o.source,...o.issues].join(' · ')]));
  else plot.append(el('p',tr('No matched field observations are available for this station.','该站暂无匹配的现场观测。')));
  const tests=rows.flatMap((r,i)=>(r?.boundary_tests||[]).map(t=>[data.cases[i].label,t.case,t.parameter,t.delta_ft.toFixed(3)]));
  if(tests.length)table(plot,[tr('Run','计算'),tr('Boundary test','边界工况'),tr('Changed input','变更输入'),'Δ WSE (ft)'],tests);
  else plot.append(el('p',tr('No verified boundary sensitivity is recorded for this station and profile.','该站本工况暂无已核验的边界敏感性结果。')));
  const lines=rows.filter(Boolean).flatMap(r=>[...(r.cutline_xy||[]),...(r.observed_xy||[]),...(r.model_xy||[]),...(r.observations||[]).map(o=>o.xy)]);
  if(!lines.length)return;
  const xs=lines.map(p=>p[0]),ys=lines.map(p=>p[1]),left=Math.min(...xs),top=Math.max(...ys);
  const scale=Math.min(704/Math.max(1,Math.max(...xs)-left),215/Math.max(1,top-Math.min(...ys)));
  const pos=p=>[18+(p[0]-left)*scale,18+(top-p[1])*scale];
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 740 250');svg.setAttribute('role','img');
  svg.setAttribute('aria-label',tr('Cross sections, observed and modeled outer wet edges, north up','断面与观测、计算最外侧湿边，北向上'));
  const colors=['#006b93','#9a4e00'];
  rows.forEach((r,i)=>{if(!r?.cutline_xy)return;
   svgEl(svg,'polyline',{points:r.cutline_xy.map(p=>pos(p).join(',')).join(' '),fill:'none',stroke:colors[i],'stroke-width':2,'stroke-dasharray':i?'7 3':''});
   (r.observed_xy||[]).forEach(p=>{const [x,y]=pos(p);svgEl(svg,'rect',{x:x-6,y:y-6,width:12,height:12,fill:'none',stroke:'#27793c','stroke-width':2});});
   (r.model_xy||[]).forEach(p=>{const [cx,cy]=pos(p);svgEl(svg,'circle',{cx,cy,r:i?3:5,fill:colors[i]});});
   (r.observations||[]).forEach(o=>{const [x,y]=pos(o.xy);svgEl(svg,'polygon',{points:[[x,y-6],[x+6,y],[x,y+6],[x-6,y]].map(p=>p.join(',')).join(' '),fill:'#86358c'});});
  });plot.append(svg,el('p',tr('North up. Green squares: mapped edge. Blue circles: base wet edge. Orange circles: alternative. Positive shortfall means water mapped beyond the modeled wet edge.',
   '北向上。绿框为历史边线，蓝点为基准计算湿边，橙点为备选。正差表示历史边线在计算湿边以外。')));
 }
 station.onchange=update;update();
 if(data.preview||!comparisonToken||comparisonToken!==current.extent_review?.sha256)return;
 const actions=details(parent,'Review decision','处理决定');
 actions.append(el('p',tr('Purple diamonds locate field observations. A request records the selected station for field follow-up.','紫色菱形表示实测位置。需补测时，会记录当前站号供现场回访。')));
 const note=field(actions,'extent-note','Decision or outstanding question (optional)','取舍依据或待查问题（可选）','','textarea');note.maxLength=1200;
 const choices=[['keep_first','Retain first run as comparison reference','保留首个计算作为对照'],['defer','Defer the choice','暂缓取舍'],['request_survey','Request field survey at this station','登记该站补测']];
 if(data.classification==='NATIVE_GEOMETRY_COMPARISON'&&data.max_wse_change)choices.push(['prefer_second','Record preference for second run','记录倾向第二方案（保留原模型）']);
 for(const [choice,en,zh] of choices){
  actions.append(button(en,zh,async()=>{
   const saved=await api('extent-decision',{...key(),decision:choice,station:station.value,reason:note.value});current=await api('project/'+identity.id);
   if(current.extent_review?.sha256===comparisonToken)identity.revision=current.revision;
   notify(tr('Decision saved for RS ','已保存处理决定，RS ')+saved.station);
  }));
 }
 if(data.classification==='NATIVE_GEOMETRY_COMPARISON'&&data.max_wse_change)actions.append(button('Use the second geometry in a new editable revision','采用第二方案几何并建立独立可编辑修订版',async()=>{
  const created=await api('revision',{...key(),confirmed:true});await open(created.id);
  notify(tr('New editable revision created. Review its inputs before computing.','已创建独立修订版，运算前请核对输入。'));
 }));
}
