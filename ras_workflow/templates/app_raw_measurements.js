'use strict';
function renderFloodMarks(parent,edition){
 const box=details(parent,'Find USGS event flood marks','查找 USGS 事件洪痕');box.id='flood-evidence';
 const call=(op,extra={})=>api('flood-'+op,{id:edition.id,revision:current.revision,...extra});
 const host=el('div');host.setAttribute('aria-live','polite');
 box.append(el('p',tr('Search by event year and official river name. Frozen marks can be reviewed offline. Elevations stay hidden during location review.','按事件年份和官方河名查询，冻结后可断网核对。定位时隐藏观测水位。')));
 const display=(out,p)=>{
  out.replaceChildren();
  out.append(el('p',p.river+' · '+p.rows.length+tr(' nearby marks in ',' 条近段洪痕，分为 ')+p.location_groups+tr(' site/coordinate groups. Different groups at the same bridge can still be dependent.',' 个站点／坐标组。同桥的不同组仍可能相关。')));
  rawPointMap(out,p);
  if(p.stations.length)table(out,[tr('Registered gage','登记水尺'),'RS',tr('Offset from outlet (m)','与出口距离 (m)'),tr('Datum','基准'),tr('Use','用途')],p.stations.map(s=>[s.station,s.matched_rs??'—',s.distance_to_boundary_center_m??'—',s.datum??'—',s.transfer_required?tr('Background; document an event-specific transfer','背景资料，需同事件传递依据'):tr('Check time and gage zero','核对时刻和水尺零点')]));
  out.append(el('small',tr('Frozen geometry SHA-256 ','冻结几何 SHA-256 ')+p.geometry_sha256));
  table(out,[tr('Event / mark / row','事件／洪痕／原始行'),tr('Site / coordinates','站点／经纬度'),tr('Location description','原件位置说明'),tr('Side / bank','桥侧／河岸'),'RS',tr('Distance to cut (m)','至断面距离 (m)'),tr('Datum / quality','基准／质量')],p.rows.map(r=>[
   [r.event,r.id,r.line].join(' / '),[r.site,...r.lonlat].join(' · '),[r.description,r.location].filter(Boolean).join(' · '),
   [r.side,r.bank].filter(Boolean).join(' · '),r.rs,String(r.cut_distance_m),[r.datum,r.quality,r.datum_matches?'':tr('Check datum','核对基准')].filter(Boolean).join(' · ')]));
  for(const s of p.sources)out.append(el('small','USGS '+s.event+' · SHA-256 '+s.sha256+' '));
  if(!p.rows.length)return;
  const groups=new Map();
  const opts=[['unresolved','Review location','待核对位置'],['outlet','Outlet control; exclude from validation','出口控制，不计核验'],['same_crossing','Same crossing; auxiliary only','同桥辅助对照'],['interior_candidate','Interior candidate; verify independence','内点候选，仍需核实独立性'],['context','Background only','仅供背景']];
  const hints={review_outlet_crossing:tr('The outlet is the nearest section for a mark in this group. Check the bridge face.','本组有洪痕最近于出口断面，请核对桥侧。'),review_gage_crossing:tr('The source identifies a gage at this crossing. Compare the event and bridge face.','原件标明同桥水尺，请核对事件和桥侧。'),review_vertical_reference:tr('Check the vertical datum and its transfer.','核对高程基准与转换依据。'),review_independent_location:tr('Check whether this interior survey was independent of calibration and outlet data.','核对本内点是否独立于调参和出口资料。')};
  out.append(el('p',tr('Identify the role of each location from its source. Use the original measurement intake for datum, timing, boundary and independent observation checks.','按原件核对各位置用途。通过原始测量表入口进一步核对基准、时刻、边界及内点独立性。')));
  for(const r of p.rows)if(!groups.has(r.group)){
   const ids=p.rows.filter(v=>v.group===r.group).map(v=>v.id).join(', ');
   out.append(el('p',hints[r.suggestion]+(r.referenced_gage?' · USGS '+r.referenced_gage:'')));
   groups.set(r.group,field(out,'flood-role-'+r.group,r.site+' · '+ids,r.site+' · '+ids,r.role,'select',opts));
  }
  out.append(button('Save location roles','保存位置用途',async()=>{
   const updated=await call('roles',{version:p.version,token:p.token,roles:Object.fromEntries([...groups].map(([k,v])=>[k,v.value]))});
   display(out,updated);notify(tr('Location roles saved','位置用途已保存'));
  }));
 };
 box.append(button('Open flood evidence','打开洪痕资料',async()=>{
  const state=await call('inspect');host.replaceChildren();
  const year=field(host,'flood-year','Year of the flood','洪水发生年份','','text');
  const river=field(host,'flood-river','Official river name (for example, Floyd River)','官方英文河名（如 Floyd River）','','text');
  const events=el('div'),out=el('div');
  year.oninput=()=>events.replaceChildren();
  host.append(button('List USGS events','查询 USGS 事件',async()=>{
   const y=year.value.trim(),found=await call('catalog',{year:y});events.replaceChildren();
   const picks=new Map();
   if(!found.events.length)events.append(el('p',tr('No events listed for this year. Check the year or use the field table.','本年度无登记事件，可核对年份或使用原始测量表。')));
   for(const e of found.events)picks.set(e.id,field(events,'flood-event-'+e.id,e.name+' · '+e.start.slice(0,10),e.name+' · '+e.start.slice(0,10),'','checkbox'));
   if(picks.size)events.append(button('Download, locate and freeze selected marks','下载、定位并冻结所选洪痕',async()=>{
    const ids=[...picks].filter(([,v])=>v.checked).map(([k])=>k);
    if(!river.value.trim()||!ids.length)throw Error(tr('Enter the river name and choose an event','请填写河名并勾选事件'));
    display(out,await call('capture',{year:y,river:river.value,events:ids,catalog_hash:found.catalog_hash}));
   }));
  }),events);
  if(state.versions.length){
   const v=field(host,'flood-version','Frozen search','冻结查询',state.versions[0],'select',state.versions.map(s=>[s,s,s]));
   host.append(button('Replay from local originals','本机原件离线重放',async()=>display(out,await call('replay',{version:v.value}))));
  }
  host.append(out);
 }),host);
}
function rawPointMap(parent,preview){
 const points=preview.rows.filter(r=>r.xy),cuts=preview.cuts;
 if(!points.length||!cuts.length)return;
 const coords=[...points.map(r=>r.xy),...cuts.flatMap(c=>c.xy)];
 const xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]);
 const xmin=Math.min(...xs),ymin=Math.min(...ys);
 const scale=Math.min(566/(Math.max(...xs)-xmin||1),266/(Math.max(...ys)-ymin||1));
 const xy=p=>[16+(p[0]-xmin)*scale,284-(p[1]-ymin)*scale];
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 600 300');svg.setAttribute('width','100%');
 svg.setAttribute('role','img');svg.setAttribute('aria-label',tr('Model sections and source rows','模型断面与测量原始行'));parent.append(svg);
 for(const c of cuts)svgEl(svg,'polyline',{points:c.xy.map(p=>xy(p).join(',')).join(' '),fill:'none',stroke:'#667986','stroke-width':1.3});
 for(const p of points){const [cx,cy]=xy(p.xy),node=svgEl(svg,'circle',{cx,cy,r:4,fill:p.issues.length?'#a84422':p.role==='outlet'?'#925610':'#006e81'});
 svgEl(node,'title',{}).textContent='RS '+p.rs+' · '+tr('source row ','原始行 ')+p.line;}
 parent.append(el('small',tr('Section lines · teal = interior · ochre = outlet · red = check source','断面线 · 青色为内点 · 棕色为出口 · 红色需核对原件')));
}
function renderRawMeasurements(parent,edition){
 const box=details(parent,'Import an original measurement table','导入原始测量表');box.id='raw-measurements';
 const host=el('div');host.setAttribute('aria-live','polite');box.append(host);
 const call=(action,extra={})=>api('raw-'+action,{id:edition.id,revision:current.revision,...extra});
 box.append(button('Start from my field table','从我的测量表开始',async()=>{
  await save();const state=await call('inspect');host.replaceChildren();
  const invert=edition.model_type!=='river';
  host.append(el('p',tr('Model reference for comparison: ','模型参考基准供核对：')+[state.crs,state.datum].filter(Boolean).join(' · ')));
  if(state.stations.length){
   table(host,[tr('Registered gage','已登记测站'),'RS',tr('Distance to outlet','至出口距离'),tr('Use','用途')],
    state.stations.map(s=>[s.station,s.matched_rs??'—',s.distance_to_boundary_center_m==null?'—':s.distance_to_boundary_center_m+' m',
     [s.datum||'—',s.datum_check==='CONVERSION_REQUIRED'?tr('Document the datum conversion','需基准转换依据'):'',
      s.transfer_required?tr('Context until event transfer is documented','须有同事件传递依据，当前仅供背景'):tr('Check event and gage zero','核对事件与水尺零点')].filter(Boolean).join(' · ')]));
  }
  if(invert)for(const f of state.invert_fields)host.append(el('p',tr(f.label.en,f.label.zh)+' · '+(f.value??'—')+' ft · '+(f.classification||tr('Missing','缺失'))));
  host.append(el('p',invert?tr('Supply group and separate inlet/outlet elevations, or group, end and elevation. Leave unmeasured ends blank.','填写涵孔组及进、出口两列涵底，或使用组号、端别、高程三列。未测端留空。'):tr('Compare points with the located sections. Before computing, use only the directly surveyed outlet. After computing, return the unused interior observations in a revision.','和已定位断面对照。计算前可采用出口原位测点，计算后再将未用于调参的内点回传至修订版。')));
  const file=field(host,'raw-file',invert?'Original UTF-8 CSV / TSV':'Original CSV / TSV or USGS field-visit GeoJSON',invert?'原始 UTF-8 CSV／制表符表':'原始 CSV／制表符表或 USGS 测验 GeoJSON','','file');file.accept=invert?'.csv,.tsv,.txt':'.csv,.tsv,.txt,.json,.geojson';
  const mode=invert?null:field(host,'raw-mode','What the elevation column measures','高程列的测量含义','stage','select',[['stage','Absolute water elevation','绝对水面高程'],['gage','Relative gage reading','相对水尺读数']]);
  const editor=el('div');file.onchange=()=>editor.replaceChildren();if(mode)mode.onchange=()=>editor.replaceChildren();
  host.append(button('Read columns and suggest matches','读取表头并建议匹配',async()=>{
   const f=file.files[0];if(!f||f.size>2000000)throw Error(tr('Select a table under 2 MB','请选择 2 MB 以内的测量表'));
   const [doc]=await encodeFiles([f]),input={...doc,mode:mode?.value||'invert'};
   const found=await call('columns',input);editor.replaceChildren();
   editor.append(el('p',found.count+tr(' source rows. Confirm units, reference systems and event against the field original. Model defaults are suggestions.',' 个原始数据行。请按测量原件确认单位、基准及事件，模型预填项仅供参考。')));
   for(const r of found.references)editor.append(el('p',r.file+' · '+Object.values(r.values).join(' · ')));
   const mapping=details(editor,'Review column assignments','核对列名匹配'),cols={},options=[['','Unassigned','未指定'],...found.headers.map(h=>[h,h,h])];
   const labels={x:['Easting / X','横坐标'],y:['Northing / Y','纵坐标'],level:['Measured elevation or reading','水位／读数／高程'],group:['Group number (1-based)','涵孔组号（从 1 起）'],end:['Inlet / outlet','进出口端别'],level_in:['Inlet invert','进口涵底'],level_out:['Outlet invert','出口涵底'],profile:['Profile','工况'],event:['Event','事件'],date:['Date','日期'],flow:['Discharge','流量'],flow_unit:['Flow unit','流量单位'],unit:['Elevation unit','高程单位'],crs:['Horizontal CRS','平面坐标系'],datum:['Vertical datum','高程基准'],uncertainty:['Vertical uncertainty','垂直不确定度'],station:['Gage ID','水尺站号']};
   const keys=invert?['group','end','level','level_in','level_out','unit','datum']:['x','y','level','profile','event','date','flow','flow_unit','unit','crs','datum','uncertainty','station'];
   const out=el('div'),invalidate=()=>out.replaceChildren();
   for(const k of keys)cols[k]=field(mapping,'raw-column-'+k,...labels[k],found.mapping[k]||'','select',options,invalidate);
   if(found.gage_json){mapping.hidden=true;editor.append(el('p',tr('USGS mean gage heights. Record numbers are 1-based GeoJSON feature positions; flow is paired by station and visit.','USGS 实测相对水尺读数。编号为从 1 起的 GeoJSON 要素序号，流量按站号及测次配对。')));}
   const settings={},grid=el('div',undefined,'grid');editor.append(grid);
   for(const k of (invert?['unit','datum']:['profile','event','date','flow','flow_unit','unit','crs','datum','uncertainty'])){
    const opts={profile:state.profiles.map(p=>[p.id,p.id,p.id]),unit:[['ft','International ft','国际英尺'],['m','Metres','米'],['us_survey_ft','US survey ft','美国测量英尺']],flow_unit:[['cfs','cfs','cfs'],['m3/s','m³/s','m³/s']]}[k];
    settings[k]=field(grid,'raw-meta-'+k,...labels[k],found.suggestions[k]??'',opts?'select':'text',opts?[['','Choose','请选择'],...opts]:null,invalidate);
   }
   if(!invert)editor.append(el('small',tr('Source columns take precedence over these defaults. The flow must match the selected model profile.','原表非空列优先于此处填写的信息。事件流量须与模型工况相符。')));
   editor.append(button('Locate and preview source rows','定位并预览原始行',async()=>{
    const pick=obj=>Object.fromEntries(Object.entries(obj).map(([k,v])=>[k,v.value]));
    const body={...input,settings:pick(settings),columns:pick(cols)},p=await call('preview',body);
    out.replaceChildren();out.append(el('p',p.raw_count+tr(' rows · eligible source rows: ',' 行 · 本次可选行：')+new Set(p.selectable).size+' · '+tr('outside section centers: ','断面中心范围外：')+p.outside_count));
    if(p.missing.length)out.append(el('p',tr('Still need survey evidence: ','仍需测量依据：')+p.missing.join(', '),'warning'));
    if(!invert)rawPointMap(out,p);
    const choices=new Map(),reasons={DATUM_MISMATCH:'Datum mismatch / 高程基准不一致',UNIT_REQUIRED:'Supply source units / 缺测量单位',EVENT_REQUIRED:'Supply event and date / 缺事件日期',DISCHARGE_MISMATCH:'Check event flow / 核对事件流量',GAGE_REQUIRES_REGISTER:'Check gage zero, datum and site transfer in the register / 核对水尺零点、基准和异地传递',DUPLICATE_POINT:'Repeated coordinates / 坐标重复',DUPLICATE_TARGET:'Repeated invert / 同端重复',CHECK_REPEATED_ROWS:'Check duplicates / 核对重复行',AMBIGUOUS_NEAREST:'Tied nearest points / 多行同距',GROUP_OR_END_REQUIRED:'Identify group and end / 需组号及端别'};
   const tableRows=p.rows.map(r=>[r.line,r.target||('RS '+(r.rs??'—')),r.value??'—',r.unit||'—',r.meta?.date||'—',r.meta?.flow?String(r.meta.flow)+' '+r.meta.flow_unit:'—',r.issues.map(i=>reasons[i]||i).join(' · ')||({interior:tr('Interior','内点'),outlet:tr('Outlet; excluded from scoring','出口，不计入评分'),invert:tr('Invert','涵底')}[r.role]||'—'),(r.nearby_lines||[]).join(', ')]);
    table(out,[tr('Record','原始行／要素'),tr('Location','位置'),tr('Value','读数'),tr('Unit','单位'),tr('Date','日期'),tr('Event flow','事件流量'),tr('Use or issue','用途或问题'),tr('Other nearby lines','其他邻近行')],tableRows);
    if(!p.selectable.length){out.append(el('p',tr('Review the source, column assignments or evidence register. No input changed.','请核对原件、列名或资料清单。本次预览未改动模型。')));return;}
    for(const n of new Set(p.selectable)){const cb=field(out,'raw-pick-'+n,'Use source row '+n,'采用原始行 '+n,'','checkbox');cb.checked=true;choices.set(n,cb);}
    const ack=field(out,'raw-ack',p.role==='interior'?'I confirm these interior points were held out from calibration and boundary inputs':'I verified the selected rows and their metadata',p.role==='interior'?'确认这些内点未用于设边界或调参':'已核对所选行、单位和基准','','checkbox');
    const uncertain=p.role==='outlet'&&p.rows.some(r=>p.selectable.includes(r.line)&&!r.meta.uncertainty);
    const conditional=uncertain?field(out,'raw-conditional','Use the outlet with unknown vertical accuracy for conditional screening','明确同意以未知垂直精度的出口作条件性初筛','','checkbox'):null;
    out.append(button(state.computed?'Create editable revision':'Save selected measurements',state.computed?'建立可编辑修订版':'保存所选实测输入',async()=>{
     if(!ack.checked)throw Error(tr('Confirm the source rows and intended use first','请先核对并确认所选原始行和用途'));
     const result=await call('apply',{...body,token:p.token,lines:[...choices].filter(([,cb])=>cb.checked).map(([n])=>n),confirmed:true,independent:p.role==='interior',conditional:!!conditional?.checked});
     await open(result.id);notify(tr('Measurements saved. Review affected inputs before running.','实测资料已保存，请核对受影响的输入后再计算。'));
    },'primary'));
   }),out);
  }),editor);
 }));
}
