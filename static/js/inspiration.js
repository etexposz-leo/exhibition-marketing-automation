'use strict';
window.renderInspiration=async function(root,ctx){
const{api,make,panel,button,selected,openFields,data}=ctx;
root.append(panel('文案灵感库','展会搭建 · 展台设计 · 参展营销。保存公开内容线索、来源和分析，转入现有草稿审核流程。'));
const status=make('p','正在读取文案库…');status.setAttribute('role','status');root.append(status);
try{
const state=await api('/api/marketing/inspiration');if(!status.isConnected)return;
status.textContent='';
const info=panel('采集范围与数据来源','按关键词主动搜索公开索引，无需提供链接。各平台收录范围不同；YouTube 可读取公开互动数据，其余结果没有可靠互动证据时标为待核验。热门候选仅代表满足您设置的门槛，不保证传播效果。');
info.append(make('p',state.platforms.map(p=>p.id).join(' · ')),make('p','正文提取组件：'+state.engine));root.append(info);
const form=make('form');form.className='card';form.append(make('h2','采集公开文案'));
function field(parent,label,type,name){const wrapper=make('label',label),input=make(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.name=name;if(type==='checkbox'){input.style.width='auto';input.style.marginLeft='12px';wrapper.style.display='flex';wrapper.style.alignItems='center';wrapper.style.justifyContent='flex-start';}wrapper.append(input);parent.append(wrapper);return input;}
const discovery=make('form');discovery.className='card';discovery.append(make('h2','主动发现热门文案'));
const keyword=field(discovery,'行业关键词','text','keyword');keyword.value='展台设计 展会搭建';keyword.required=true;keyword.minLength=2;keyword.maxLength=120;
const dp=make('select'),dl=make('label','搜索平台');dp.setAttribute('aria-label','搜索平台');dl.append(dp);discovery.append(dl);dp.append(new Option('全部平台（依次搜索）','all'),...state.platforms.map(p=>new Option(p.id,p.id)));
const views=field(discovery,'最低播放量（与点赞门槛满足其一）','number','views');views.value=10000;views.min=1;
const minlikes=field(discovery,'最低点赞数','number','minlikes');minlikes.value=100;minlikes.min=1;
const days=field(discovery,'最近多少天','number','days');days.value=730;days.min=1;days.max=3650;
const go=make('button','开始发现'),stop=make('button','停止后续搜索');go.type='submit';stop.type='button';stop.disabled=true;discovery.append(go,stop);
const progress=make('p');progress.setAttribute('role','status');discovery.append(progress);let cancelled=false;stop.onclick=()=>{cancelled=true;stop.disabled=true;};
discovery.onsubmit=async e=>{e.preventDefault();go.disabled=true;stop.disabled=false;cancelled=false;let report=[];const platforms=dp.value==='all'?state.platforms.map(p=>p.id):[dp.value];try{for(const id of platforms){if(cancelled||!progress.isConnected)break;progress.textContent=report.join('；')+' 正在搜索 '+id+'…';const began=Date.now();try{const r=await api('/api/marketing/inspiration/discover',{platform:id,keyword:keyword.value,limit:3,min_views:Number(views.value),min_likes:Number(minlikes.value),max_age_days:Number(days.value)});report.push(id+': '+r.status+'，新增 '+r.saved+'，热门候选 '+r.popular_candidates);}catch(err){report.push(id+': '+err.message);}await reload();progress.textContent=report.join('；');if(platforms.length>1&&!cancelled)await new Promise(resolve=>setTimeout(resolve,Math.max(0,5100-(Date.now()-began))));}}finally{go.disabled=false;stop.disabled=true;progress.textContent=report.join('；')+(cancelled?' 已停止后续搜索。':'');}};
root.append(discovery);
const brand=make('form');brand.className='card';brand.append(make('h2','ET EXPO 原创事实库'),make('p','仅填写我们的真实服务、案例和优势。生成器不能把参考帖的客户、业绩、数字移作我们的事实。'));
const facts=field(brand,'已核实的品牌事实（每行一条）','textarea','facts');facts.required=true;facts.minLength=10;facts.maxLength=4000;facts.value=state.brand_facts?.facts||'';
const confirmed=field(brand,'我确认上述事实属于 ET EXPO','checkbox','confirmed');confirmed.required=true;
const savefacts=make('button','保存品牌事实');savefacts.type='submit';brand.append(savefacts);brand.onsubmit=async e=>{e.preventDefault();savefacts.disabled=true;try{await api('/api/marketing/inspiration/brand-facts',{facts:facts.value,confirmed:confirmed.checked});status.textContent='品牌事实已加密保存。';}catch(err){status.textContent=err.message;}finally{savefacts.disabled=false;}};root.append(brand);
const composer=panel('原创创作设置','参考受众问题和内容结构，重新立意和表达。重合筛查仅覆盖保存的参考摘要，不是全网查重，也不能替代人工核对。');
const mode=make('select'),ml=make('label','生成方式');mode.setAttribute('aria-label','生成方式');ml.append(mode);composer.append(ml);mode.append(new Option('本地原创模板（非 AI）','local'));if(state.ai_available)mode.append(new Option('AI 原创创作','ai'));else composer.append(make('p','AI 尚未配置：可使用本地模板，AI 功能不会假装成功。'));
const dest=make('select'),destlabel=make('label','草稿平台');dest.setAttribute('aria-label','草稿平台');destlabel.append(dest);composer.append(destlabel);dest.append(...['linkedin','facebook','instagram','tiktok','xiaohongshu','douyin'].map(x=>new Option(x,x)));
const lang=make('select'),ll=make('label','文案语言');lang.setAttribute('aria-label','文案语言');ll.append(lang);composer.append(ll);lang.append(new Option('中文','zh'),new Option('English','en'));
const angle=field(composer,'新的切入角度（AI 模式）','text','angle');angle.maxLength=500;root.append(composer);
const aid=make('details');aid.className='card';aid.append(make('summary','安全配置 AI 服务（仅本地 Owner）'));const aif=make('form');aid.append(aif);const provider=make('select');provider.setAttribute('aria-label','AI 服务');provider.append(new Option('OpenAI','openai'),new Option('DeepSeek','deepseek'));aif.append(provider);const key=field(aif,'API Key（只在本页输入，不要发到聊天）','password','ai_key');key.autocomplete='off';key.required=true;key.minLength=16;key.maxLength=2048;const ais=make('button','加密保存 AI 配置');ais.type='submit';aif.append(make('p','保存不调用供应商。选择 AI 生成时，品牌事实与参考摘要会发送到所选服务，并可能产生 API 费用。'),ais);aif.onsubmit=async e=>{e.preventDefault();ais.disabled=true;try{await api('/api/marketing/inspiration/ai-settings',{provider:provider.value,key:key.value});key.value='';if(!Array.from(mode.options).some(x=>x.value==='ai'))mode.append(new Option('AI 原创创作','ai'));status.textContent='AI 配置已加密保存；尚未验证供应商连接。';}catch(err){key.value='';status.textContent=err.message;}finally{ais.disabled=false;}};root.append(aid);
const preview=make('div');root.append(preview);
async function compose(row){if(!selected())throw Error('请先在顶部选择或创建活动。');status.textContent='正在生成原创预览…';const r=await api('/api/marketing/inspiration/rewrite',{source_id:row.id,campaign_id:Number(selected()),platform:dest.value,language:lang.value,mode:mode.value,angle:angle.value});preview.replaceChildren();const f=make('form');f.className='card';f.append(make('h2','原创预览 · '+(r.mode==='ai'?'AI 创作':'本地模板')),make('p',r.originality.status+' · 仅检查参考摘要；编辑后保存时重新检查。'));const caption=field(f,'原创文案（可编辑）','textarea','original_caption');caption.value=r.caption;caption.minLength=20;caption.maxLength=10000;caption.required=true;const check=field(f,'已核对事实、案例归属和原创表达','checkbox','facts_reviewed');check.required=true;const save=make('button','存入待审核草稿');save.type='submit';f.append(save);f.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api('/api/marketing/inspiration/rewrite/save-draft',{proposal_id:r.id,caption:caption.value,facts_reviewed:check.checked});status.textContent='已存入 Content Queue，状态 DRAFT，未发布。';f.replaceChildren(make('p','已保存，请在 Content Queue 中刷新并审核。'));}catch(err){status.textContent=err.message;}finally{save.disabled=false;}};preview.append(f);status.textContent='原创预览已生成，请核对后保存。';preview.scrollIntoView({block:'nearest'});}
const url=field(form,'公开内容链接（HTTPS）','url','url');url.required=true;url.maxLength=2000;url.placeholder='https://…';
const submit=make('button','抓取此链接');submit.type='submit';form.append(submit);
form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;status.textContent='正在检查来源并提取正文，请稍候…';try{const result=await api('/api/marketing/inspiration/capture',{url:url.value});status.textContent=result.duplicate?'此来源已存在，保留原审核状态。':'已保存来源摘要；热度仍需核实。';await reload();}catch(err){status.textContent=err.message;}finally{submit.disabled=false;}};
root.append(form);
const details=make('details');details.className='card';details.append(make('summary','导入已有文案摘要（适用于未开放抓取的平台）'));
const imported=make('form');details.append(imported);
const source=field(imported,'原始来源链接','url','source');source.required=true;
const title=field(imported,'标题','text','title');title.maxLength=300;
const excerpt=field(imported,'有权限使用的摘要（40–400 字符）','textarea','excerpt');excerpt.required=true;excerpt.minLength=40;excerpt.maxLength=400;
const likes=field(imported,'看到的点赞数（可留空，保存为人工提供、未验证）','number','likes');likes.min='0';likes.max='1000000000000';likes.step='1';
const importButton=make('button','导入摘要');importButton.type='submit';imported.append(importButton);
imported.onsubmit=async e=>{e.preventDefault();importButton.disabled=true;try{const result=await api('/api/marketing/inspiration/import',{url:source.value,title:title.value,excerpt:excerpt.value,likes:likes.value===''?null:Number(likes.value)});status.textContent=result.duplicate?'该来源已经存在。':'摘要已导入，数据来源标为人工提供。';await reload();}catch(err){status.textContent=err.message;}finally{importButton.disabled=false;}};
root.append(details);
const filters=make('div',null,'toolbar'),search=field(filters,'搜索标题 / 文案 / 来源','search','search'),platform=make('select'),review=make('select');
const plabel=make('label','平台');plabel.append(platform);filters.append(plabel);platform.append(new Option('全部平台',''),...state.platforms.map(p=>new Option(p.id,p.id)));
const slabel=make('label','审核状态');slabel.append(review);filters.append(slabel);review.append(new Option('全部状态',''),new Option('待审核','PENDING_REVIEW'),new Option('已收藏','SAVED'),new Option('已拒绝','REJECTED'));root.append(filters);
const heatfilter=make('select');heatfilter.setAttribute('aria-label','热度证据筛选');heatfilter.append(new Option('全部热度状态',''),new Option('热门候选','POPULAR_CANDIDATE'),new Option('待核验','UNVERIFIED'),new Option('未达门槛','BELOW_THRESHOLD'));filters.append(heatfilter);const list=make('div');root.append(list);let items=state.items;
async function reload(){items=(await api('/api/marketing/inspiration')).items;draw();}
function draw(){list.replaceChildren();const rows=items.filter(x=>(!heatfilter.value||(x.heat_status||'UNVERIFIED')===heatfilter.value)&&(!platform.value||x.platform===platform.value)&&(!review.value||x.status===review.value)&&JSON.stringify(x).toLowerCase().includes(search.value.toLowerCase()));
if(!rows.length){list.append(panel('暂无匹配文案','点击“开始发现”按行业关键词搜索。空列表不会生成演示内容。'));return;}
for(const row of rows){const card=panel(row.title||'来源摘要',row.platform+' · '+row.status+' · '+(row.heat_status==='POPULAR_CANDIDATE'?'热门候选':row.heat_status==='BELOW_THRESHOLD'?'未达热门门槛':row.heat_status==='OUTSIDE_WINDOW'?'时间范围外':'热度未验证'));card.append(make('p','播放量：'+(row.metrics.views??'未知')+' · '+(row.heat_evidence?.reasons||[]).join('；')));
const link=make('a','查看原始来源');link.href=row.source_url;link.target='_blank';link.rel='noopener noreferrer';card.append(link,make('p','来源时间：'+(row.published_at||'未知')+' · 采集时间：'+row.captured_at),make('p','采集方式：'+row.capture_method+' · 点赞：'+(row.metrics.likes??'未知')+' · 证据：'+row.metrics_source));
card.append(make('div',row.excerpt,'body'),make('p','主题命中：'+(row.topic_matches.join('、')||'需人工确认相关性')),make('p','结构分析（规则提取，非 AI 结论）：'+row.analysis.opening+' · '+(row.analysis.has_numbers?'含数字':'未发现数字')),make('p',row.analysis.note));
const notes=field(card,'审核备注','textarea','notes');notes.value=row.notes||'';notes.maxLength=2000;
const actions=make('div',null,'actions');card.append(actions);
for(const[label,next] of [['收藏 / 保存备注','SAVED'],['拒绝','REJECTED'],['恢复待审核','PENDING_REVIEW']])button(actions,label,async()=>{await api('/api/marketing/inspiration/'+row.id+'/review',{revision:row.revision,status:next,notes:notes.value});await reload();});
button(actions,'起草原创文案',()=>compose(row));
list.append(card);}}
search.oninput=draw;platform.onchange=draw;review.onchange=draw;heatfilter.onchange=draw;draw();
}catch(err){status.textContent=err.message;}
};
