'use strict';
window.renderExpoCrawler=async function(root,ctx){
 const {api,make,panel,button,identity}=ctx,base='/api/marketing/modules/crawler',perms=new Set(identity.permissions),host=make('div');root.append(host);
 let selected='',view='Saved Crawl Jobs',timer;
 const can=p=>perms.has('CRAWLER_'+p);
 await window.renderOriginalSoftware?.(root,ctx,'crawler');
 const error=e=>{const p=make('p',e.message);p.setAttribute('role','alert');host.prepend(p);};
 function form(title,fields,submit){const box=panel(title),f=make('form');box.append(f);for(const [name,value,type='text']of fields){const label=make('label',name),input=make(type==='textarea'?'textarea':'input');input.name=name;input.type=type; if(type==='checkbox')input.checked=!!value;else input.value=value||'';label.append(input);f.append(label);}const send=make('button','保存');send.type='submit';f.append(send);button(f,'取消',()=>box.remove());f.onsubmit=async e=>{e.preventDefault();send.disabled=true;try{const v=Object.fromEntries(new FormData(f));for(const el of f.querySelectorAll('input[type=checkbox]'))v[el.name]=el.checked;await submit(v);box.remove();await load();}catch(e){error(e);}finally{send.disabled=false;}};host.prepend(box);}
 async function load(){if(!root.contains(host))return;const data=await api(base);host.replaceChildren();
  const intro=panel('ExpoCrawler','公开来源 → 人工审核 → 线索/展会日历/外链。审核不发送邮件、不报价。后台服务持续采集；关闭页面不停止任务。服务需要保持运行，重启后恢复待执行任务。');host.append(intro);intro.append(make('p','Background worker: '+(data.worker?.running?'RUNNING':'NOT RUNNING')+(data.worker?.last_error?' · '+data.worker.last_error:'')));
  const tabs=['New Crawl','Saved Crawl Jobs','Running','Completed','Failed','Manual Review','Export','Trade Show Calendar','Quote Drafts'];const nav=make('div',null,'actions');intro.append(nav);for(const t of tabs)button(nav,t,()=>{view=t;load();},view===t?'active':'');
  if(view==='New Crawl'){if(!can('CONFIGURE')){host.append(make('p','需要 CRAWLER_CONFIGURE 权限'));return;}form('新建公开采集任务',[['name',''],['source_url',''],['trade_show',''],['show_url',''],['start_date','','date'],['end_date','','date'],['venue',''],['city',''],['state',''],['country',''],['source_type','OFFICIAL_EXHIBITOR_LIST'],['max_pages','10','number'],['terms_reviewed',false,'checkbox']],async v=>{v.max_pages=Number(v.max_pages);await api(base+'/jobs',v);view='Saved Crawl Jobs';});return;}
  if(view==='Trade Show Calendar'){const events=await api(base+'/calendar');host.append(panel('本地展会日历','已审核官方来源；不写入网站，不覆盖已有活动。'));for(const e of events)host.append(panel(e.trade_show,[e.start_date,e.end_date,e.venue,e.city,e.show_url].filter(Boolean).join(' · ')));return;}
  if(view==='Quote Drafts'){host.append(panel('报价交接草稿','尚未证明 Quote Robot 接收接口；以下仅为本地待导入草稿，没有价格。'));for(const q of Object.values(data.quote_drafts))host.append(panel(q.company,JSON.stringify(q,null,2)));return;}
  if(view==='Manual Review'){const records=data.records.filter(r=>!selected||data.jobs.find(j=>j.id===selected)?.record_ids.includes(r.id));host.append(make('p','记录数 '+records.length));button(host,'查看全部结果',()=>{selected='';load();});
   for(const r of records){const p=panel(r.company_name||r.trade_show||r.source_url,r.status);const details=make('pre',JSON.stringify(r,null,2));details.style.whiteSpace='pre-wrap';details.style.overflowWrap='anywhere';p.append(details);host.append(p);
    if(can('APPROVE_RESULTS')){for(const [a,l]of [['approve','Approve'],['reject','Reject']])button(p,l,async()=>{await api(base+'/records/'+r.id+'/review',{revision:r.revision,action:a});await load();});button(p,'Edit',()=>form('编辑（修改后需重新审核）',['trade_show','show_url','start_date','end_date','venue','city','country','company_name','company_website','booth_number','contact_name','contact_title','business_email','phone'].map(k=>[k,r[k]]),v=>api(base+'/records/'+r.id+'/review',{revision:r.revision,action:'edit',fields:v})));
     if(r.status==='APPROVED')for(const [target,label,confirmation]of [['leads','Create / Link Lead','public_business_confirmed'],['calendar','Add to Local Calendar','official_verified'],['backlinks','Add Backlink Opportunity',null],['quote','Create Quote Handoff Draft','qualified']])button(p,label,()=>form(label,confirmation?[[confirmation,false,'checkbox']]:[],v=>api(base+'/records/'+r.id+'/transfer',{revision:r.revision,target,...v})));
    }
   }return;
  }
  const filter={'Running':'RUNNING','Completed':'COMPLETED','Failed':'FAILED'}[view];
  for(const j of data.jobs.filter(j=>!filter||j.status===filter)){const p=panel(j.name,j.status);p.append(make('p',[j.source_url,j.trade_show,j.venue,j.city,j.start_date,j.end_date].filter(Boolean).join(' · ')),make('p','Started '+(j.started_at||'—')+' · Completed '+(j.completed_at||'—')+' · Records '+j.records_found+' · Errors '+j.errors+' · '+(j.last_error||'')));host.append(p);
   if(can('RUN'))for(const [a,l,states]of [['start','Start',['SAVED']],['pause','Pause',['RUNNING']],['resume','Resume',['PAUSED']],['retry','Retry',['FAILED','MANUAL_ACTION_REQUIRED']],['cancel','Cancel',['SAVED','RUNNING','PAUSED','FAILED','MANUAL_ACTION_REQUIRED']]])if(states.includes(j.status))button(p,l,async()=>{await api(base+'/jobs/'+j.id+'/action',{action:a});await load();});
   button(p,'View Results',()=>{selected=j.id;view='Manual Review';load();});if(can('EXPORT'))for(const format of ['json','csv','xlsx']){const a=make('a','Export '+format.toUpperCase());a.href=base+'/export/'+j.id+'?fmt='+format;a.style.marginRight='1rem';p.append(a);}
  }
  if(data.jobs.some(j=>j.status==='RUNNING')){clearTimeout(timer);timer=setTimeout(()=>{if(root.contains(host))load().catch(error);},3000);}

 }
 await load().catch(error);
};
