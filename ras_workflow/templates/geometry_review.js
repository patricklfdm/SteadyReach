'use strict';
let geometryIndex=0, geometryMode=null, geometryPicks=null;
function geometryReason(code){const names={SCALE_SENSITIVE_BANKS:["Banks change with smoothing scale","岸站随平滑尺度变化"],NO_SCALE_STABLE_BANK_PAIR:["No stable bank pair across scales","不同尺度下未形成稳定岸站对"],BANK_WIDTH_DISCONTINUITY:["Abrupt bank-width change along reach","沿程岸宽突变"],NO_DISTINCT_BANK_ON_ONE_OR_BOTH_SIDES:['No distinct bank on one or both sides','一侧或两侧缺少明确岸顶'],COMPETING_LEFT_BANKS:['Multiple plausible left banks','左岸存在多个候选'],COMPETING_RIGHT_BANKS:['Multiple plausible right banks','右岸存在多个候选'],ASYMMETRIC_BANK_RELIEF:['Bank heights are strongly asymmetric','两侧岸高明显不对称'],CHANNEL_MINIMUM_OFF_CENTER:['Channel minimum is away from the cut centre','槽底偏离断面中心'],LOW_OUTER_TERRAIN_OR_MULTIPLE_CHANNELS:['Low outer terrain or multiple channels','外侧低地或多槽'],INVALID_OR_NODATA_PROFILE:['Missing or invalid elevation samples','高程样点缺失或无效'],DISTINCT_SLOPE_BREAKS_REVIEW_REQUIRED:['Distinct slope changes; review required','坡折较明确，仍须复核'],INTERSECTING_SECTIONS:['Cross sections intersect','断面相交'],SELF_INTERSECTING_CUT:['Cutline crosses itself','断面线自交'],ZERO_LENGTH_CUT_SEGMENT:['Zero-length segment','零长度线段']};return names[code]?tr(...names[code]):code;}
function terrainReview(screen){
 const review=data.geometry_review, rows=review?.sections||[];
 if(!rows.length)return;
 const box=el('section',undefined,'card');box.id='terrain-review';
 box.append(el('h3',tr('Terrain sections and bank review','地形断面与岸站复核')),
 el('p',tr('Bank suggestions are morphological estimates, not bankfull levels. Review each retained section. Crossings and NoData must be resolved before approval.','岸站建议来自地形形态，不代表满岸水位。需复核每个保留断面；相交和 NoData 必须先处理。')));
 const controls=el('div',undefined,'actions'),filter=el('select'),choice=el('select');
 filter.setAttribute('aria-label',tr('Section filter','断面筛选'));choice.setAttribute('aria-label',tr('Cross section','断面'));
 filter.append(new Option(tr('All sections','全部断面'),'all'),new Option(tr('Uncertain / blocked','不确定 / 有阻塞'),'uncertain'),new Option(tr('Needs review','待复核'),'pending'));
 const accepted=i=>rows[i].terrain_review?.fingerprint===review.fingerprints[i];
 const uncertain=i=>['LOW','UNRESOLVED'].includes(rows[i].bank_candidates?.confidence)||review.issues.some(q=>q.sections.includes(i))||(review.physical_screen?.issues||[]).some(q=>!q.sections.length||q.sections.includes(i));
 const confidence=r=>r.bank_candidates?.confidence==='LOW'?tr('Low confidence','低置信度'):r.bank_candidates?.confidence==='MEDIUM'?tr('Moderate confidence','中等置信度'):tr('Unresolved','无法明确识别');
 const populate=()=>{choice.replaceChildren();rows.forEach((r,i)=>{if(filter.value==='uncertain'&&!uncertain(i)||filter.value==='pending'&&accepted(i))return;choice.append(new Option((accepted(i)?'✓ ':uncertain(i)?'! ':'')+'XS '+(i+1)+' · RS '+(r.rs??'—')+' · '+confidence(r),i));});if([...choice.options].some(o=>Number(o.value)===geometryIndex))choice.value=geometryIndex;else geometryIndex=Number(choice.value||0);draw();};
 const map=document.createElementNS('http://www.w3.org/2000/svg','svg'),chart=document.createElementNS('http://www.w3.org/2000/svg','svg');
 for(const svg of [map,chart]){svg.setAttribute('viewBox','0 0 700 240');svg.setAttribute('role','img');svg.style.width='100%';svg.style.maxHeight='260px';svg.style.border='1px solid #ccd8db';}
 map.setAttribute('aria-label',tr('Section layout in projected coordinates','投影坐标下的断面分布'));chart.setAttribute('aria-label',tr('Sampled cross-section profile','断面采样剖面'));
 const editor=el('div'),candidates=el('div'),info=el('p'),issues=el('ul'),bankText=el('p'),actions=el('div',undefined,'actions'),name=el('input'),basis=el('textarea');
 name.id='section-reviewer';name.value=data.draft.reviewer||'';basis.id='section-basis';basis.rows=2;
 function draftChoice(){data.draft.section_review_drafts??={};data.draft.section_review_drafts[review.fingerprints[geometryIndex]]={bank_indices:geometryPicks?.slice()||null,reviewer:name.value,basis:basis.value};changed();}
 name.oninput=draftChoice;basis.oninput=draftChoice;
 const sideButtons=[0,1].map(side=>button(side===0?tr('Pick left bank','选择左岸'):tr('Pick right bank','选择右岸'),()=>{geometryMode=geometryMode===side?null:side;mode();}));
 function mode(){sideButtons.forEach((b,i)=>{b.classList.toggle('primary',geometryMode===i);b.setAttribute('aria-pressed',String(geometryMode===i));});const row=rows[geometryIndex],current=row.bank_stations_ft?.map(v=>row.station_ft.indexOf(v))||null;bankText.textContent=tr('Selected sample indices (zero-based): ','已选择采样索引（从零开始）：')+JSON.stringify(geometryPicks)+(JSON.stringify(current)!==JSON.stringify(geometryPicks)?tr(' · Draft selection; confirm this section to apply.',' · 草稿选择，确认此断面后才应用。'):'');}
 function svgNode(parent,tag,attrs){let n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);parent.append(n);return n;}
 function plot(){
  const row=rows[geometryIndex];map.replaceChildren();chart.replaceChildren();
  const points=rows.flatMap(r=>r.cutline_xy||[]).filter(p=>p.length===2&&p.every(Number.isFinite));
  if(points.length){const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),lo=[Math.min(...xs),Math.min(...ys)],span=Math.max(Math.max(...xs)-lo[0],Math.max(...ys)-lo[1],1),scale=210/span;
   rows.forEach((r,i)=>{if(!(r.cutline_xy||[]).every(p=>p.length===2&&p.every(Number.isFinite)))return;const line=svgNode(map,'polyline',{points:r.cutline_xy.map(p=>[250+(p[0]-lo[0])*scale,225-(p[1]-lo[1])*scale].join(',')).join(' '),fill:'none',stroke:i===geometryIndex?'#b14122':uncertain(i)?'#b88212':'#297889','stroke-width':i===geometryIndex?4:2});line.style.cursor='pointer';line.onclick=()=>{geometryIndex=i;geometryMode=null;geometryPicks=null;filter.value='all';populate();};});
   svgNode(map,'text',{x:12,y:22}).textContent=tr('Grid N ↑ · click a section','格网北 ↑ · 点击断面');}
  const x=row.station_ft||[],z=row.elevation_ft||[],valid=z.filter(Number.isFinite);if(!valid.length||x.length<2)return;
  const low=Math.min(...valid),height=Math.max(Math.max(...valid)-low,1),project=(i)=>[30+(x[i]-x[0])/(x.at(-1)-x[0])*640,195-(z[i]-low)/height*160];
  let segment=[];const flush=()=>{if(segment.length)svgNode(chart,'polyline',{points:segment.join(' '),fill:'none',stroke:'#665039','stroke-width':2});segment=[];};
  x.forEach((v,i)=>{if(!Number.isFinite(z[i])){flush();return;}segment.push(project(i).join(','));});flush();
  x.forEach((v,i)=>{if(!Number.isFinite(z[i]))return;const p=project(i),picked=geometryPicks?.includes(i),suggested=row.bank_candidates?.selected_indices?.includes(i);const n=svgNode(chart,'circle',{cx:p[0],cy:p[1],r:picked?6:suggested?5:3,fill:picked?'#c06a00':suggested?'#7943a6':'#297889'});svgNode(n,'title',{}).textContent=i+': '+v.toFixed(3)+' / '+z[i].toFixed(3)+' ft';n.style.cursor='pointer';n.onclick=()=>{if(geometryMode===null||i===0||i===x.length-1)return;geometryPicks??=[null,null];geometryPicks[geometryMode]=i;draftChoice();plot();mode();};});
  svgNode(chart,'text',{x:30,y:227}).textContent=tr('Station / elevation: international ft. Purple: suggested; orange: selected.','站距 / 高程：国际英尺。紫色为建议，橙色为当前选择。');
 }
 function draw(){if(!choice.options.length){info.textContent=tr('No sections match this filter.','当前筛选无断面。');chart.replaceChildren();map.replaceChildren();return;}
  const r=rows[geometryIndex],p=r.bank_candidates,draft=data.draft.section_review_drafts?.[review.fingerprints[geometryIndex]];geometryMode=null;geometryPicks=draft?draft.bank_indices?.slice()||null:r.bank_stations_ft?.map(v=>r.station_ft.indexOf(v))||null;
  info.textContent=(accepted(geometryIndex)?tr('Reviewed · ','已复核 · '):tr('Pending · ','待复核 · '))+confidence(r)+' · '+(p?.reasons||[]).map(geometryReason).join('; ');
  issues.replaceChildren();for(const q of review.issues.filter(q=>q.sections.includes(geometryIndex)))issues.append(el('li',geometryReason(q.code)+' · XS '+q.sections.map(i=>i+1).join(', ')));for(const q of review.physical_screen?.issues||[]){if(!q.sections.length||q.sections.includes(geometryIndex))issues.append(el('li',tr(q.en,q.zh)+geometryEvidence(q.evidence)));}
  basis.value=draft?.basis||r.terrain_review?.basis||'';name.value=draft?.reviewer||r.terrain_review?.reviewer||data.draft.reviewer||'';
  candidates.replaceChildren();for(const [side,key] of [[0,'left'],[1,'right']]){const select=el('select');select.setAttribute('aria-label',side===0?tr('Left bank alternatives','左岸候选'):tr('Right bank alternatives','右岸候选'));select.append(new Option(side===0?tr('Other left-bank candidates','其他左岸候选'):tr('Other right-bank candidates','其他右岸候选'),''));for(const v of p?.[key]||[])select.append(new Option(v.station_ft.toFixed(2)+' ft · '+tr('scale support ','尺度支持 ')+(v.scale_support??1)+'/3',v.index));select.onchange=()=>{if(select.value==='')return;geometryPicks??=[null,null];geometryPicks[side]=Number(select.value);draftChoice();plot();mode();};candidates.append(select);}
  editor.replaceChildren();geometryEditPanel(editor,geometryIndex,review.fingerprints[geometryIndex],r,name,basis);plot();mode();}
 actions.append(...sideButtons,button(tr('Preview suggested banks','预览建议岸站'),()=>{geometryPicks=rows[geometryIndex].bank_candidates?.selected_indices?.slice()||null;geometryMode=null;draftChoice();plot();mode();}),button(tr('Clear selection','清除选择'),()=>{geometryPicks=null;geometryMode=null;draftChoice();plot();mode();}));
 const nameLabel=el('label',tr('Reviewer','复核人'));nameLabel.htmlFor=name.id;const basisLabel=el('label',tr('Section review basis / uncertainty treatment','断面复核依据 / 不确定性处理'));basisLabel.htmlFor=basis.id;
 const decide=action=>{if(!choice.options.length)throw Error(tr('Select a visible section first.','请先选择一个可见断面。'));const index=geometryIndex,fingerprint=review.fingerprints[index],picks=geometryPicks?.slice(),who=name.value,note=basis.value;return operation(async()=>applyResponse(await request('section-review',{revision:data.draft.revision,index,fingerprint,bank_indices:picks,reviewer:who,basis:note,action})));};
 controls.append(filter,choice);box.append(controls,map,chart,info,issues,actions,candidates,bankText,nameLabel,name,basisLabel,basis,
 button(tr('Confirm this section','确认此断面'),()=>decide('ACCEPT'),'primary'),button(tr('Exclude this section (record reason)','排除此断面（记录原因）'),()=>decide('EXCLUDE'),'danger'),editor);
 filter.onchange=populate;choice.onchange=()=>{geometryIndex=Number(choice.value);draw();};screen.append(box);geometryIndex=Math.min(geometryIndex,rows.length-1);populate();
}

function geometryEvidence(e){
 const parts=[],n=v=>Number(v).toFixed(2);
 if(e.sides)parts.push(tr('Low ends: ','低端点：')+e.sides.map(s=>s==='left'?tr('left','左'):tr('right','右')).join(', '));
 if(e.low_spans_ft)parts.push(tr('Low station intervals: ','低地区间：')+e.low_spans_ft.map(p=>p.map(n).join('–')+' ft').join('; '));
 if(e.reach_lengths_ft)parts.push(tr('Left / channel / right lengths: ','左滩 / 主槽 / 右滩长度：')+e.reach_lengths_ft.map(n).join(' / ')+' ft');
 if(e.widths_ft)parts.push(tr('Section widths: ','断面宽度：')+e.widths_ft.map(n).join(' / ')+' ft');
 if(e.intersections!==undefined)parts.push(tr('Crossings: ','穿越次数：')+(e.intersections??tr('unavailable','未取得')));
 return parts.length?' '+parts.join('; '):'';
}
