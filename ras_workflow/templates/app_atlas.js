'use strict';
function atlasNumber(value){return Number.isFinite(value)?value.toFixed(3):'—';}
function atlasSelected(rows,profile,scope,search){return rows.filter(r=>(!profile||r.profile===profile)&&(scope==='all'||r.needs_attention)&&(!search||r.rs.includes(search)||r.issues.some(i=>i.code.toLowerCase().includes(search.toLowerCase()))));}

function atlasSectionPlot(parent,row){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 250');svg.classList.add('repair-profile');svg.setAttribute('aria-label',tr('Computed section, banks and water levels','计算断面、岸站和水位'));parent.append(svg);
 const x=row.station_ft,z=row.elevation_ft,levels=[row.wse_ft,row.egl_ft,row.critical_wse_ft].filter(Number.isFinite),lo=Math.min(...z,...levels),hi=Math.max(...z,...levels),px=v=>45+(v-x[0])/Math.max(1,x.at(-1)-x[0])*620,py=v=>190-(v-lo)/Math.max(1,hi-lo)*160;
 profileGrid(svg,x,lo,hi,[45,665,30,190]);
 for(const [a,b]of row.wet_intervals_ft||[])svgEl(svg,'rect',{x:px(a),y:228,width:px(b)-px(a),height:7,fill:'#007da5'});
 svgEl(svg,'polyline',{points:x.map((v,i)=>px(v)+','+py(z[i])).join(' '),fill:'none',stroke:'#745b3b','stroke-width':2});
 for(const [level,color,dash]of [[row.wse_ft,'#007da5',''],[row.egl_ft,'#ae5516','6,3'],[row.critical_wse_ft,'#8a428e','2,3']])if(Number.isFinite(level))svgEl(svg,'line',{x1:45,x2:665,y1:py(level),y2:py(level),stroke:color,'stroke-width':2,'stroke-dasharray':dash});
 for(const v of row.banks_ft.filter(Number.isFinite))svgEl(svg,'line',{x1:px(v),x2:px(v),y1:30,y2:190,stroke:'#65712a','stroke-dasharray':'4,4'});
 parent.append(el('p',tr('Brown: native ground · Blue: WSE · Orange dashed: EGL · Purple dotted: critical WSE, when available · Olive: model banks. Blue bars below the axis show geometric wet intervals.','棕色：原生地面 · 蓝色：水位 · 橙色虚线：能量线 · 紫色点线：临界水位（若有）· 橄榄色：模型岸站。轴下蓝条表示几何湿区。'),'muted'));
}

function atlasMap(parent,row,lookup,crs){
 const group=[row,...row.neighbors.map(n=>lookup.get(n.section_id)).filter(Boolean)].filter(r=>r.map);
 if(!row.map){parent.append(el('p',tr('Projected section correspondence is unavailable; the native profile remains available above.','投影断面位置对应不可用；仍可查看上方原生剖面。'),'warning'));return;}
 const points=group.flatMap(r=>r.map.cutline_xy),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),lx=Math.min(...xs),ly=Math.min(...ys),hx=Math.max(...xs),hy=Math.max(...ys),scale=Math.min(320/Math.max(1,hx-lx),265/Math.max(1,hy-ly)),cx=(lx+hx)/2,cy=(ly+hy)/2,px=v=>215+(v-cx)*scale,py=v=>165-(v-cy)*scale;
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 700 330');svg.classList.add('repair-profile');svg.setAttribute('aria-label',tr('Bound section locations and wet intervals','封存断面位置与几何湿区'));parent.append(svg);
 for(const [index,other]of group.entries()){const m=other.map,active=other.section_id===row.section_id,color=active?'#a4428c':'#9b9b9b';svgEl(svg,'polyline',{points:m.cutline_xy.map(p=>px(p[0])+','+py(p[1])).join(' '),fill:'none',stroke:color,'stroke-width':active?3:1});
  for(const segment of m.wet_segments_xy||[])svgEl(svg,'polyline',{points:segment.map(p=>px(p[0])+','+py(p[1])).join(' '),fill:'none',stroke:'#007da5','stroke-width':active?4:2,opacity:active?1:.5});
  for(const p of m.banks_xy||[])svgEl(svg,'circle',{cx:px(p[0]),cy:py(p[1]),r:active?4:2,fill:'#b79d11',stroke:'#333'});
  const a=m.cutline_xy[0],labelY=70+index*75;svgEl(svg,'polyline',{points:px(a[0])+','+py(a[1])+' 425,'+labelY+' 445,'+labelY,fill:'none',stroke:color,'stroke-width':1,'stroke-dasharray':'3,3'});
  const label=svgEl(svg,'text',{x:450,y:labelY+4,fill:'#333','font-size':13});label.textContent='RS '+other.rs+(active?tr(' (selected)','（当前）'):'');
 }
 svgEl(svg,'line',{x1:650,x2:650,y1:290,y2:245,stroke:'#333','stroke-width':1});svgEl(svg,'polyline',{points:'645,253 650,245 655,253',fill:'none',stroke:'#333'});svgEl(svg,'text',{x:636,y:235,'font-size':12}).textContent=tr('Grid N','格网北');
 parent.append(el('p',tr('Local projected plan (north up): ','局部投影平面（北向上）：')+(crs||'—')+tr('. Blue segments are section/WSE intersections, not connected flow paths or inundation. Yellow dots are model banks.','. 蓝色线段为断面与计算水位的交集，不代表相连过流路径或淹没范围；黄点为模型岸站。'),'muted'));
}

function renderResultAtlas(parent){
 const box=guidanceTarget(details(parent,'Computed section review / warning locations','计算断面复核／警告定位'),'atlas'),output=el('div');box.append(output);
 const id=current.id,hash=current.summary.sha256;let loading=false,loaded=false;
 async function load(){
  if(loading||loaded)return;loading=true;output.setAttribute('aria-busy','true');output.replaceChildren(el('p',tr('Reading verified native sections, water levels and warning locations…','正在读取已核验原生断面、水位及警告位置…'),'status'));
  try{const data=await api('qa-atlas',{id,summary_hash:hash});if(!output.isConnected||current?.id!==id||current.summary?.sha256!==hash)return;loaded=true;render(data);}
  catch(error){if(output.isConnected&&current?.id===id){output.replaceChildren(el('p',tr('Section review is unavailable: ','断面复核暂不可用：')+error.message,'warning'),button('Retry section review','重试读取断面',load));}}
  finally{loading=false;output.removeAttribute('aria-busy');}
 }
 function render(data){
  output.replaceChildren();output.append(el('p',data.sections.length+tr(' section/profile records · ',' 条断面／工况记录 · ')+data.attention_section_profiles+tr(' with warnings or geometric observations · ',' 条带警告或几何观察 · ')+data.located_diagnostic_count+'/'+data.diagnostic_count+tr(' diagnostic records located.',' 条诊断已定位。'),'status'));
  output.append(el('p',tr('These are sealed calculation inputs and outputs. No geometry is changed and no warning is closed. Separate wet areas do not prove effective conveyance or connection along the reach.','此处读取封存的计算输入与输出，不修改几何或关闭警告。分隔湿区不能证明有效过流或沿河段连通。'),'warning'));
  for(const error of data.source_errors)output.append(el('p',error,'warning'));
  output.append(el('p',tr('Native warning coverage: ','原生警告覆盖：')+data.warning_coverage));
  if(data.unlocated_issues.length){const other=details(output,'Messages without a unique section ('+data.unlocated_issues.length+')','无法唯一定位到断面的信息（'+data.unlocated_issues.length+'）');table(other,['Profile','RS','Code','Message'],data.unlocated_issues.map(i=>[i.profile??'—',i.station??'—',i.code,i.evidence?.native_message||i.recommended_action]));}
  const controls=el('div');output.append(controls);
  const profile=field(controls,'atlas-profile','Profile','工况','','select',[['','All profiles','全部工况'],...[...new Set(data.sections.map(r=>r.profile))].map(v=>[v,v,v])]);
  const scope=field(controls,'atlas-scope','Show','显示','attention','select',[['attention','Warnings / observations','警告／几何观察'],['all','All computed sections','全部计算断面']]);
  const search=field(controls,'atlas-search','RS or warning code','断面编号或警告代码',''),count=el('p','', 'status'),list=el('div');output.append(count,list);
  const lookup=new Map(data.sections.map(r=>[r.section_id,r])),nodes=new Map();
  const navigate=target=>{profile.value=target.profile;scope.value='all';search.value='';draw();const node=nodes.get(target.section_id);node.parentElement.open=true;node.scrollIntoView({block:'start',behavior:'smooth'});notify(tr('Opened computed RS ','已打开计算断面 RS ')+target.rs);};
  function draw(){list.replaceChildren();nodes.clear();const rows=atlasSelected(data.sections,profile.value,scope.value,search.value.trim());count.textContent=rows.length+tr(' matching sections. Expand one to see its native message, profile and neighbors.',' 条匹配断面；展开即可查看原生信息、剖面及邻近断面。');
   for(const row of rows){const panel=details(list,row.profile+' · RS '+row.rs+' · '+row.issues.length+' messages',row.profile+' · RS '+row.rs+' · '+row.issues.length+' 条信息');nodes.set(row.section_id,panel);let drawn=false;
    const detail=()=>{if(drawn||!panel.parentElement.open)return;drawn=true;
     table(panel,[tr('Metric','指标'),tr('Native result','原生结果')],[['WSE ft',atlasNumber(row.wse_ft)],['EGL ft',atlasNumber(row.egl_ft)],[tr('Critical WSE ft','临界水位 ft'),atlasNumber(row.critical_wse_ft)],[tr('Channel velocity ft/s','主槽流速 ft/s'),atlasNumber(row.velocity_fts)],['Fr',atlasNumber(row.froude)],[tr('Minimum error ft','最小误差 ft'),atlasNumber(row.min_error_ft)],[tr('Left / right bank ft','左／右岸站 ft'),row.banks_ft.map(atlasNumber).join(' / ')],[tr('Left / right edge exceedance ft','左／右端点超出水深 ft'),[row.left_excess_ft,row.right_excess_ft].map(atlasNumber).join(' / ')]]);
     for(const issue of row.issues){panel.append(el('p',issue.code+' · '+issue.severity,'warning'));panel.append(el('p',issue.evidence?.native_message||issue.recommended_action));}
     atlasSectionPlot(panel,row);
     if(row.wet_intervals_ft===null)panel.append(el('p',tr('WSE unavailable; no wet-interval inference was made.','水位不可用，未推算湿区。'),'warning'));else table(panel,[tr('Geometric wet interval','几何湿区'),tr('From ft','起点 ft'),tr('To ft','终点 ft'),tr('Width ft','宽度 ft')],row.wet_intervals_ft.map(([a,b],i)=>[i+1,atlasNumber(a),atlasNumber(b),atlasNumber(b-a)]));
     atlasMap(panel,row,lookup,data.horizontal_crs);
     table(panel,[tr('Neighbor','邻近断面'),'RS','WSE ft','EGL ft','V ft/s','Fr',tr('Channel distance ft','主槽间距 ft')],row.neighbors.map(n=>[tr(n.relation,n.relation==='upstream'?'上游':'下游'),n.rs,atlasNumber(n.wse_ft),atlasNumber(n.egl_ft),atlasNumber(n.velocity_fts),atlasNumber(n.froude),atlasNumber(n.channel_length_between_ft)]));
     for(const n of row.neighbors)panel.append(button('Open '+n.relation+' RS '+n.rs,'打开'+(n.relation==='upstream'?'上游':'下游')+' RS '+n.rs,()=>navigate(lookup.get(n.section_id))));
     const codes=new Set(row.issues.map(v=>v.code));const tools=[];
     if((row.left_excess_ft||0)>0||(row.right_excess_ft||0)>0)tools.push(['coverage','Review section coverage','核对断面覆盖']);
     if([...codes].some(v=>/ENERGY|CONVEYANCE|VELOCITY|CRITICAL|MINIMUM_ERROR/.test(v)))tools.push(['spacing','Review spacing / energy solution','核对间距／能量解']);
     if(row.wet_intervals_ft?.length>1||codes.has('NATIVE_DIVIDED_FLOW'))tools.push(['revision','Review banks and actual flow paths','核对岸站与真实过流路径']);
     for(const [key,en,zh]of tools)panel.append(button(en,zh,()=>openGuidanceTool(key)));
    };panel.parentElement.addEventListener('toggle',detail);detail();
   }
  }
  profile.onchange=draw;scope.onchange=draw;search.oninput=draw;draw();
 }
 box.parentElement.addEventListener('toggle',()=>{if(box.parentElement.open)void load();});if(box.parentElement.open)void load();
}
