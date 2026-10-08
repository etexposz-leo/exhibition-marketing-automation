'use strict';
window.renderQuoteWorkspace=async function(root,ctx){
 const {api,make,panel,button}=ctx,base='/api/marketing/modules/quote';
 const status=make('p','读取报价工作区…');status.setAttribute('role','status');root.append(status);
 const area=make('div');root.append(area);
 await window.renderOriginalSoftware?.(root,ctx,'quote');
 async function load(){
  const s=await api(base);if(!root.isConnected)return;area.replaceChildren();status.textContent='AI 报价机器人 · 板块内操作 · 不启动桌面软件';
  const guard=panel('报价工作区',s.template_verified?'原始模板哈希已核验。项目资料与报价 Excel 分开标记；不会自动采用历史价格或发送客户。':'模板缺失或哈希变化，暂停创建。');
  guard.append(make('p','当前阶段：接收资料、编辑项目、导出资料封面。正式报价工作簿生成仍需价格审批及真实重开验证。'));area.append(guard);
  button(guard,'新建项目资料',()=>form(null));
  const sources=panel('已批准的 ExpoCrawler 资料');for(const r of s.approved_sources){const row=panel(r.company,r.show+' · 展位 '+r.booth);const a=make('a','查看原始来源');a.href=r.source_url;a.target='_blank';a.rel='noopener noreferrer';row.append(a);button(row,'接收到报价工作区',async()=>{const result=await api(base+'/from-crawler/'+encodeURIComponent(r.id),{});await load();status.textContent=result.duplicate?'该来源已接收，没有重复创建。':'原报价程序已接收项目资料；报价 Excel 尚未生成。'});sources.append(row)}area.append(sources);
  const projects=panel('本地项目');for(const p of s.projects){const c=panel(p.fields.company,p.fields.show+' · '+p.fields.booth);c.append(make('p','状态：项目资料草稿 · 正式报价 Excel：未生成'));const details=make('dl');for(const[label,key]of [['展位尺寸','booth_size'],['年份','year'],['客户模式','customer_mode'],['联系人','contact'],['邮箱','email'],['备注','notes']])details.append(make('dt',label),make('dd',p.fields[key]||'待填写'));c.append(details);button(c,'编辑项目资料',()=>form(p));
   for(const [name,label]of [['project_info.xlsx','下载项目资料'],['project_info_cover.xlsx','下载资料封面'],['source-provenance.json','下载来源记录']]){const a=make('a',label);a.href=base+'/projects/'+p.id+'/files/'+name;a.download=name;c.append(a,make('span','　'))}
   button(c,'在板块内预览资料封面',()=>{const frame=make('iframe');frame.title='项目资料封面预览';frame.src=base+'/projects/'+p.id+'/preview';frame.style.width='100%';frame.style.height='650px';frame.setAttribute('sandbox','');c.append(frame)});
   c.append(make('p','继续生成前仍需：'+p.missing.join('、')));const generate=button(c,'生成正式报价 Excel',()=>{});generate.disabled=true;generate.title='资料、价格审批和工作簿验证尚未满足，禁止自动报价';projects.append(c)}if(!s.projects.length)projects.append(make('p','从已批准展商资料接收，或新建项目资料。'));area.append(projects);
 }
 function form(project){
  const c=panel(project?'编辑项目资料':'新建项目资料'),f=make('form');c.append(f);area.prepend(c);
  for(const[label,key]of [['公司 / 参展商','company'],['展会名称','show'],['展位号','booth'],['展位尺寸（未知留空）','booth_size'],['年份','year'],['联系人','contact'],['邮箱','email'],['备注','notes']]){const l=make('label',label),e=make(key==='notes'?'textarea':'input');e.name=key;e.value=project?.fields[key]||'';e.setAttribute('aria-label',label);if(['company','show'].includes(key))e.required=true;l.append(e);f.append(l)}
  const l=make('label','客户报价模式'),sel=make('select');sel.name='customer_mode';sel.setAttribute('aria-label','客户报价模式');for(const[v,t]of [['','待确认'],['Exhibition Agent','展会代理'],['Regular Client','普通客户']]){const o=make('option',t);o.value=v;sel.append(o)}sel.value=project?.fields.customer_mode||'';l.append(sel);f.append(l);
  const save=make('button','保存项目资料');save.type='submit';f.append(save);button(f,'取消',()=>c.remove());f.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api(base+'/projects'+(project?'/'+project.id:''),Object.fromEntries(new FormData(f)));await load();status.textContent='项目资料已保存，未生成或发送报价。'}catch(error){status.textContent=error.message;save.disabled=false}};c.scrollIntoView({block:'start',behavior:'smooth'});
 }
 try{await load()}catch(e){status.textContent=e.message}
};
