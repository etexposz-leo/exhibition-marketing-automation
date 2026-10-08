'use strict';
window.renderBacklinkOpportunities=async function(root,ctx){
 const {api,make,panel,button}=ctx,base='/api/marketing/backlinks/opportunities';
 const note=make('p');note.role='status';root.append(note);const body=make('div');root.append(body);
 async function action(p){try{await api(base,p);await load()}catch(e){note.textContent=e.message}}
 async function load(){const s=await api(base);if(!body.isConnected)return;body.replaceChildren();
  note.textContent='美国白帽外链机会 · 规则依据评估（非模型判断）· 审批不执行提交';
  const summary=panel('Backlink Opportunity Manager');for(const [k,v]of Object.entries(s.counts))summary.append(make('span',k+': '+v+'　'));
  button(summary,'发现美国外链机会',()=>action({action:'discover'}));const dl=make('a','导出 CSV');dl.href=base+'.csv';summary.append(dl);body.append(summary);
  const filters=panel('筛选');const search=make('input');search.placeholder='域名 / 联系人 / 行业 / 来源';search.setAttribute('aria-label','搜索外链');const select=make('select');select.setAttribute('aria-label','状态');for(const t of ['',...s.statuses]){const o=make('option',t||'所有状态');o.value=t;select.append(o)}filters.append(search,select);body.append(filters);const list=make('div');body.append(list);
  const draw=()=>{list.replaceChildren();for(const r of s.items.filter(r=>(!select.value||r.status===select.value)&&JSON.stringify(r).toLowerCase().includes(search.value.toLowerCase()))){const c=panel(r.domain,r.status+' · '+r.source_type+' · '+r.country+' · Risk '+r.spam_risk);const details=make('details'),heading=make('summary','查看完整信息 / 证据');details.append(heading);for(const k of s.fields)details.append(make('p',k+': '+(r[k]||'—')));if(r.last_check_result)details.append(make('p','检查结果: '+r.last_check_result));c.append(details);
   button(c,'编辑 / 审核',()=>edit(r,s));button(c,'Approve',()=>action({id:r.id,revision:r.revision,action:'approve'}));button(c,'Reject',()=>action({id:r.id,revision:r.revision,action:'reject'}));
   if(r.status==='APPROVED')button(c,'标记准备提交',()=>action({id:r.id,revision:r.revision,action:'ready'}));
   if(r.status==='READY_TO_SUBMIT')button(c,'登记人工提交（不会代发）',()=>receipt(r));
   if(['SUBMITTED','LIVE','LOST','FAILED'].includes(r.status))button(c,'检查链接',()=>action({id:r.id,action:'check'}));list.append(c)}};search.oninput=draw;select.onchange=draw;draw();
  const jobs=panel('后台发现 / 检查任务（服务运行时自动处理，LIVE 每 7 天复查）');for(const j of s.jobs)jobs.append(make('p',j.kind+' · '+j.status+' · '+j.created_at+(j.results!==undefined?' · 处理 '+j.results+' 页':'')));body.append(jobs);
 }
 function form(title,fields,save){const c=panel(title),f=make('form');c.append(f);body.prepend(c);for(const [key,value]of Object.entries(fields)){const label=make('label',key),input=make('textarea');input.name=key;input.value=value||'';label.append(input);f.append(label)}const submit=make('button','保存');submit.type='submit';f.append(submit);button(f,'取消',()=>c.remove());f.onsubmit=async e=>{e.preventDefault();await save(Object.fromEntries(new FormData(f)))};c.scrollIntoView({block:'start'})}
 function edit(r,s){const allowed=s.fields.filter(k=>!['domain','source_url','status','submitted_at','approved_at','live_url','last_checked_at'].includes(k));form('编辑会撤销原审批；country 填 US，spam_risk 填 LOW / MEDIUM / HIGH / UNKNOWN',Object.fromEntries(allowed.map(k=>[k,r[k]])),fields=>action({id:r.id,revision:r.revision,action:'edit',fields}))}
 function receipt(r){form('仅登记你已在外部完成的人工提交；请填写真实证据',{live_url:'',receipt_note:''},fields=>action({id:r.id,revision:r.revision,action:'submitted',...fields}))}
 await load();const timer=setInterval(()=>{if(!body.isConnected){clearInterval(timer);return}if(!body.querySelector('form'))load().catch(e=>note.textContent=e.message)},30000);
};
