'use strict';
// DOM text only: neither generated copy nor source material is rendered as HTML.
window.renderSalesCopy = async function(root, ctx) {
  const {api, make, panel, button, selected, identity} = ctx;
  const base = '/api/marketing/sales-copy';
  root.classList.add('sales-workspace');
  const intro = panel('Sales Copy Engine · 销售文案引擎', '素材 → Sales Brief → 平台版本 → Quality Gates → 人工预览 → 批准 → 现有发布队列');
  intro.append(make('p', 'REAL 发布关闭。批准只保存审核结果；不会发帖。Website 仅生成本地内容包。', 'sales-safety'));
  root.append(intro);
  if (!selected()) { root.append(panel('先选择 Campaign', '从上方选择现有活动，或新建活动。每个活动独立保存素材、Brief、文案版本与审核记录。')); return; }
  const campaignId = selected();
  const error = make('p', '', 'danger'); error.setAttribute('role', 'status'); root.append(error);
  try {
    const [options, memory] = await Promise.all([api(base+'/options'), api(base+'/campaigns/'+campaignId)]);
    const canWrite = ['OWNER','ADMIN','STAFF','REVIEWER'].includes(identity.role);
    const canReview = ['OWNER','ADMIN'].includes(identity.role);
    const form = panel('1 / Sales Brief', '先确认受众、意图、相关痛点和证据，再生成。未填写痛点时，根据话题选择 2–4 项。');
    const grid = make('div', null, 'sales-fields'); form.append(grid);
    const fields = {};
    const choices = {
      cta_type: options.cta_types, tone:['professional','conversational','founder_style','project_story','technical','sales','direct','educational'],
      length:['short','medium','long'], sales_intensity:['low','medium','high'], creativity:['low','medium','high'], content_type:options.content_types
    };
    const labels = {target_audience:'Target Audience / 目标受众',customer_type:'Customer Type',industry:'Industry',trade_show:'Trade Show',city:'City',venue:'Venue（未知留空）',booth_size:'Booth Size',market:'Market',topic:'Topic / 原始素材摘要',pain_points:'Pain Points（每行一项，2–4 项）',desired_outcome:'Desired Outcome',main_selling_point:'Main Selling Point',supporting_selling_points:'Supporting Points（每行一项）',differentiators:'Differentiators（需证据支持）',objections:'Objections（每行一项）',offer:'Offer',cta_type:'CTA Type',cta:'CTA（留空按类型生成）',tone:'Tone',length:'Length',sales_intensity:'Sales Intensity',creativity:'Creativity',content_type:'Content Type',content_goal:'Content Goal',primary_keyword:'Website Primary Keyword',secondary_keywords:'Secondary Keywords（每行一项）',asset_ids:'共享媒体 Asset IDs（每行一项）',sources:'Source References（JSON；只填已授权资料）',website:'Website SEO / GEO 元数据（JSON）'};
    const arrayFields = new Set(['pain_points','supporting_selling_points','differentiators','objections','secondary_keywords','asset_ids']);
    const defaults = {customer_type:'Brand / Exhibitor',market:'United States',desired_outcome:'A coordinated booth plan with clear responsibilities',main_selling_point:'Booth design, build and project coordination',cta_type:'consultation',tone:'professional',length:'medium',sales_intensity:'medium',creativity:'medium',content_type:'sales_post',content_goal:'Get booth consultation',sources:[],website:{}};
    const latest = memory.briefs[0];
    const initial = {...defaults, ...(latest?.brief||{})};
    for (const [name,label] of Object.entries(labels)) {
      const wrap = make('label', label);
      const input = make(choices[name]?'select':arrayFields.has(name)||['topic','sources','website'].includes(name)?'textarea':'input');
      input.name = name; input.disabled = !canWrite;
      if (choices[name]) for (const value of choices[name]) input.append(new Option(value,value));
      const value = initial[name];
      input.value = ['sources','website'].includes(name)?JSON.stringify(value||(['sources'].includes(name)?[]:{}),null,2):Array.isArray(value)?value.join('\n'):value||'';
      if (input.tagName==='TEXTAREA') input.rows=['sources','website'].includes(name)?6:3;
      wrap.append(input); grid.append(wrap); fields[name]=input;
    }
    const sourceHelp = make('details'); sourceHelp.append(make('summary','来源与 Website 元数据格式'));
    sourceHelp.append(make('pre', JSON.stringify({sources:[{reference:'owner-approved brief / project record',kind:'admin_input',text:'经核对的完整事实或句子',confirmed:false}],website:{seo_title:'',meta_description:'',h1:'',h2_h3:[],internal_links:[],image_alt:[],canonical:'',slug:'',existing_slug:'',old_url:'',new_url:'',redirect_301:'',structured_data:{},robots:'',sitemap:'',og:{},twitter:{}}},null,2)));
    sourceHelp.append(make('p','来源仅由管理员手工导入；不会抓取 CRM 或网站客户数据库。confirmed 是管理员确认，不代表系统独立核实。图片请先上传至共享素材库，再填写 Asset ID。'));
    form.append(sourceHelp);
    let briefId = latest?.id || null;
    let dirty = false;
    for (const field of Object.values(fields)) field.addEventListener('input',()=>{dirty=true;});
    function readBrief() {
      const result={};
      for (const [name,input] of Object.entries(fields)) result[name]=['sources','website'].includes(name)?JSON.parse(input.value||(['sources'].includes(name)?'[]':'{}')):arrayFields.has(name)?input.value.split('\n').map(x=>x.trim()).filter(Boolean):input.value;
      return result;
    }
    const briefPreview = make('details'); briefPreview.append(make('summary','查看内部 Sales Brief / 14 个分析阶段'));
    const briefText=make('pre',latest?JSON.stringify(latest.brief,null,2):'保存 Brief 后显示');briefPreview.append(briefText);form.append(briefPreview);
    async function saveBrief() { const r=await api(base+'/briefs',{campaign_id:campaignId,brief:readBrief()});briefId=r.id;dirty=false;briefText.textContent=JSON.stringify(r.brief,null,2);return r; }
    if (canWrite) button(form,'保存并分析 Sales Brief',async()=>{await saveBrief();error.textContent='已保存 Brief；尚未生成或发布。';});
    root.append(form);
    const generatePanel=panel('2 / Choose Platform + Generate','同一 Brief 分别适配各平台。Website 默认不勾选。');
    const checks={};
    for (const platform of options.platforms) {const label=make('label',platform,'sales-check');const input=make('input');input.type='checkbox';input.checked=platform!=='website';input.disabled=!canWrite;label.prepend(input);generatePanel.append(label);checks[platform]=input;}
    const mode=make('select');mode.setAttribute('aria-label','Generation mode');mode.append(new Option('Local · 规则草稿（不是 AI；风格精调需 AI 或人工）','local'),new Option('AI · 使用已配置服务，发送当前 Brief 与素材','ai'));generatePanel.append(mode);
    if(canWrite) button(generatePanel,'生成所选平台版本 / Regenerate',async()=>{
      if(!briefId||dirty)await saveBrief();
      const platforms=Object.keys(checks).filter(x=>checks[x].checked);
      if(!platforms.length)throw Error('至少选择一个平台');
      await api(base+'/generate',{brief_id:briefId,platforms,mode:mode.value});
      root.replaceChildren();await window.renderSalesCopy(root,ctx);
    });
    const importId=make('input');importId.type='number';importId.min='1';importId.placeholder='现有 Content Queue Draft ID';importId.setAttribute('aria-label','Existing draft ID');generatePanel.append(importId);
    if(canWrite) button(generatePanel,'导入现有草稿进入统一质量审核',async()=>{if(!briefId||dirty)await saveBrief();await api(base+'/import-draft/'+Number(importId.value),{brief_id:briefId,platforms:['linkedin']});root.replaceChildren();await window.renderSalesCopy(root,ctx);});
    root.append(generatePanel);
    const preview=panel('3 / Human Preview + Quality Gates','PASS 仍需人工批准；WARN 需要管理员明确确认并记录原因；FAIL 不可批准。编辑产生新版本并撤销旧版本的可发布状态。');root.append(preview);
    for(const row of memory.copies){
      const card=panel(row.platform.toUpperCase()+' · #'+row.id+' · '+row.status);
      card.append(make('p',`${row.gate.status} · ${row.gate.score}/100 · ${row.mode}`, 'sales-gate '+row.gate.status.toLowerCase()));
      const original=make('details');original.append(make('summary','原始版本 / Original copy'),make('pre',row.original_content));card.append(original);
      const copy=make('textarea');copy.value=row.content;copy.rows=9;copy.setAttribute('aria-label',row.platform+' copy '+row.id);copy.disabled=!canWrite||row.status==='SUPERSEDED';card.append(copy);
      card.append(make('p',[...row.gate.failures,...row.gate.warnings].join(' · ')||'没有规则检查警告'));
      const report=make('details');report.append(make('summary','Quality Report / Claims / SEO / Similarity'),make('pre',JSON.stringify(row.gate,null,2)));card.append(report);
      const reviewed=make('input');reviewed.type='checkbox';const reviewedLabel=make('label','我已预览并核对事实、来源与素材');reviewedLabel.prepend(reviewed);card.append(reviewedLabel);
      const ack=make('input');ack.type='checkbox';const ackLabel=make('label','管理员明确接受上述 WARN（不解除发布时的事实证据限制）');ackLabel.prepend(ack);card.append(ackLabel);
      const note=make('textarea');note.rows=2;note.placeholder='审核说明 / WARN 必填';note.setAttribute('aria-label','Review note '+row.id);card.append(note);
      async function refresh(){root.replaceChildren();await window.renderSalesCopy(root,ctx);}
      if(canWrite&&row.status!=='SUPERSEDED')button(card,'保存编辑并重新检查',async()=>{await api(base+'/copies/'+row.id+'/edit',{fingerprint:row.fingerprint,content:copy.value});await refresh();});
      if(canReview&&row.status!=='SUPERSEDED'){
        const approve=button(card,'Approve · 仅批准，不发布',async()=>{if(copy.value!==row.content)throw Error('请先保存编辑并重新检查');await api(base+'/copies/'+row.id+'/review',{fingerprint:row.fingerprint,action:'approve',acknowledge_warnings:ack.checked,facts_reviewed:reviewed.checked,media_reviewed:reviewed.checked,note:note.value});await refresh();});
        approve.disabled=row.gate.status==='FAIL';
        button(card,'Reject',async()=>{await api(base+'/copies/'+row.id+'/review',{fingerprint:row.fingerprint,action:'reject',note:note.value});await refresh();});
      }
      button(card,'导出内容与审核包',async()=>{const pack=await api(base+'/copies/'+row.id+'/export');const url=URL.createObjectURL(new Blob([JSON.stringify(pack,null,2)],{type:'application/json'}));const a=make('a');a.href=url;a.download='sales-copy-'+row.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      if(row.review_log.length){const log=make('details');log.append(make('summary','审核记录'),make('pre',JSON.stringify(row.review_log,null,2)));card.append(log);}
      preview.append(card);
    }
    if(!memory.copies.length)preview.append(make('p','此活动尚无文案版本。'));
    root.append(panel('Campaign Memory / Analytics','Brief、来源、素材引用、关键词、CTA 和历史版本按活动保留。GA4 / Ads / LinkedIn / Meta / Google Business / Conversion 仅预留接口契约；没有读取实际绩效，也不会自动优化。'));
  } catch(e) { error.textContent=e.message; }
};
