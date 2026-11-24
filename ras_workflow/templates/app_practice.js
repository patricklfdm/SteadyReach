'use strict';

// This optional exercise reads a small extract of three verified native runs.
// Its selections live in the browser tab and never enter a project or a solver request.
function renderPractice(parent){
 const box=details(parent,'Try a worked river example','试做一个河道算例',false,'east-fork-practice');
 const disclosure=box.parentElement;
 let loaded=false;
 const load=async()=>{
  if(loaded||!disclosure.open)return;
  loaded=true;
  box.replaceChildren(el('p',tr('Opening the recorded East Fork results…','正在读取 East Fork 的已算结果…')));
  try{
   const data=await api('east-fork-practice.json');
   if(!box.isConnected)return;
   box.replaceChildren();
   box.append(el('p',tr('East Fork River, Wyoming. Fill the missing roughness, compare two recorded HEC-RAS runs, then open the practice report. Your projects are separate.',
    '怀俄明州 East Fork 河。补选糙率，对比两次已有的 HEC-RAS 计算，然后打开练习报告。练习独立于你的工程。')));
   const key=draftKey('east-fork-practice','home'), saved=readDraft(key)||{};
   const reference=data.cases.find(row=>row.n===data.baseline_n);
   const alternatives=data.cases.filter(row=>row.n!==data.baseline_n);
   const n=field(box,'practice-n','Trial Manning’s n (baseline '+reference.n.toFixed(3)+')','试算糙率 n（基准 '+reference.n.toFixed(3)+'）',
    '', 'select',[['','Choose a recorded value','请选择已算的糙率'],...alternatives.map(row=>[String(row.n),row.n.toFixed(3),row.n.toFixed(3)])]);
   const response=el('p');response.setAttribute('aria-live','polite');box.append(response);
   const report=el('article',undefined,'practice-report');report.id='practice-report';
   const openReport=button('Open practice report','打开练习报告',()=>display(true));
   box.append(openReport,report);
   function display(show){
    const row=alternatives.find(item=>String(item.n)===n.value);
    report.replaceChildren();report.hidden=!row||!show;openReport.disabled=!row;
    if(!row){
     response.textContent=tr('Select a roughness to see the change at upstream section RS 516.','选择糙率后可查看上游断面 RS 516 的水位变化。');
     return;
    }
    const delta=rs=>{const d=row.wse_m[rs]-reference.wse_m[rs];return (d>0?'+':'')+d.toFixed(3);};
    response.textContent='RS 516 · '+reference.wse_m[516].toFixed(3)+' → '+row.wse_m[516].toFixed(3)+' m · Δ '+delta(516)+' m';
    writeDraft(key,{n:row.n,report:show});
    if(!show)return;
    report.append(el('h3',tr('East Fork River · practice comparison','East Fork 河 · 练习对比报告')),el('p',data.event+' · '+data.flow_m3s+' m³/s · '+data.datum));
    table(report,['RS',tr('Baseline','基准')+' n='+reference.n.toFixed(3)+' (m)',tr('Trial','试算')+' n='+row.n.toFixed(3)+' (m)','Δ (m)'],
     Object.keys(reference.wse_m).map(Number).sort((a,b)=>b-a).map(rs=>[rs,reference.wse_m[rs].toFixed(3),row.wse_m[rs].toFixed(3),delta(rs)]));
    report.append(el('p',tr('RS '+data.boundary_rs+' supplied the fixed downstream stage. Use the upstream sections to assess roughness response. This comparison covers the calibration event.',
     'RS '+data.boundary_rs+' 为下游给定水位。可用上游各断面判断水位对糙率的响应。本对比限于该场校准事件。')));
    const source=el('a',tr('USGS field record','USGS 现场记录'));source.href=data.source;source.target='_blank';source.rel='noopener';
    report.append(source,el('p','HEC-RAS HDF SHA-256 · n='+reference.n.toFixed(3)+' · '+reference.native_sha256,'muted'),
     el('p','HEC-RAS HDF SHA-256 · n='+row.n.toFixed(3)+' · '+row.native_sha256,'muted'));
    report.tabIndex=-1;report.focus({preventScroll:true});
   }
   n.value=alternatives.some(row=>row.n===saved.n)?String(saved.n):'';
   n.onchange=()=>{writeDraft(key,null);display(false);};
   display(!!saved.report);
  }catch(error){
   loaded=false;box.replaceChildren(el('p',error.message,'warning'),button('Retry example','重试算例',load));
  }
 };
 disclosure.addEventListener('toggle',load);
 if(disclosure.open)void load();
}
