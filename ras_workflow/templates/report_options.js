'use strict';
let reportDraft={purpose:'',reviewer:'',previous_run_id:'',criteria:[]};
function renderReportOptions(out,h,tr){
 const panel=node('details');panel.id='report-options';panel.append(node('summary',tr('Report purpose, criteria and previous run (optional)','报告用途、判据及前次运行（可选）')));out.append(panel);
 panel.append(node('p',tr('No design limits are assumed. Enter only supported criteria. Numerical satisfaction does not grant engineering acceptance. These options apply when you regenerate a report.','不预设设计限值。请填写有依据的判据；数值满足不代表工程接受。以下选项在重新生成报告时应用。')));
 for(const [key,en,zh] of [['purpose','Purpose / intended use','报告用途'],['reviewer','Criteria reviewer','判据审核人']]){const label=node('label',tr(en,zh)),input=node('input');input.id='report-'+key;input.value=reportDraft[key];input.oninput=()=>reportDraft[key]=input.value;label.append(input);panel.append(label);}
 const previous=node('select');previous.id='report-previous';previous.append(new Option(tr('No previous run comparison','不比较前次运行'),''));for(const r of h.previous_runs||[])previous.append(new Option(r.finished_at_utc+' | '+r.run_id,r.run_id));previous.value=reportDraft.previous_run_id;previous.onchange=()=>reportDraft.previous_run_id=previous.value;panel.append(node('label',tr('Compare to / hydraulic review baseline','对比运行 / 水力复核基线')),previous);
 const box=node('div');panel.append(box);
 function rows(){box.replaceChildren();reportDraft.criteria.forEach((r,i)=>{const row=node('fieldset');row.append(node('legend',tr('Criterion ','判据 ')+(i+1)));
 function select(key,label,options){const l=node('label',label),s=node('select');for(const [v,t]of options)s.append(new Option(t,v));s.value=r[key];s.onchange=()=>r[key]=s.value;l.append(s);row.append(l);}
 select('profile',tr('Profile','工况'),(h.scenario_ids||[]).map(v=>[v,v]));select('metric',tr('Metric','指标'),[['road_freeboard_ft',tr('Road margin (ft)','道路余高 (ft)')],['headwater_wse_ft',tr('Headwater (ft)','涵前水位 (ft)')],['tailwater_wse_ft',tr('Tailwater (ft)','涵后水位 (ft)')]]);select('operator',tr('Comparison','比较'),[['>=',tr('At least','至少')],['<=',tr('At most','至多')]]);
 for(const [key,label,type]of [['limit',tr('Limit','限值'),'number'],['basis',tr('Source / requirement and locator','来源 / 要求及位置'),'text']]){const l=node('label',label),v=node('input');v.type=type;v.step='any';v.value=r[key]??'';v.oninput=()=>r[key]=v.value;l.append(v);row.append(l);}
 row.append(button(tr('Remove','移除'),()=>{reportDraft.criteria.splice(i,1);rows();}));box.append(row);});}
 panel.append(button(tr('Add a criterion','添加判据'),()=>{reportDraft.criteria.push({profile:h.scenario_ids?.[0]||'',metric:'road_freeboard_ft',operator:'>=',limit:'',basis:''});rows();}));rows();
 if(h.qa_decisions)panel.append(node('p',tr('The latest submitted QA decisions will be attached; unsent draft decisions are not a submission.','报告将附上最近已提交的 QA 决定；未提交草稿不算提交。')));
 panel.append(node('p',tr('Unit / datum: ','单位 / 基准：')+(h.report_units?.unit||'—')+' / '+(h.report_units?.datum||'—')));
}
function reportContext(h){
 if(!reportDraft.purpose.trim()&&!reportDraft.reviewer.trim()&&!reportDraft.criteria.length&&!reportDraft.previous_run_id)return null;
 return {...reportDraft,criteria:reportDraft.criteria.map(r=>{if(r.limit===''||!Number.isFinite(Number(r.limit)))throw Error(lang==='zh'?'判据限值不能为空。':'Criterion limit is required.');return {...r,limit:Number(r.limit),unit:h.report_units?.unit,datum:h.report_units?.datum};})};
}
