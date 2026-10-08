'use strict';
window.renderPublishingCenter = async function(root, ctx) {
  const {api, make, panel, button, selected} = ctx;
  const base='/api/marketing/publishing-center';
  const intro=panel('发布中心 · 国际 / 中国', '选择平台 → 分平台文案与素材 → 一键预检。当前为本地准备版，批量真实发布尚未开放。');
  intro.append(make('p','已添加平台目录不等于已接通账号。网站内容仍使用原 Sales Copy Engine。'));
  root.append(intro);
  try {
    const state=await api(base+'/catalog');
    const choices=[];
    const selection=make('p','已选 0 个平台'); intro.append(selection);
    const results=panel('预检结果','预检不会上传素材、排队或调用第三方接口。');
    const invalidate=()=>{selection.textContent='已选 '+choices.filter(x=>x.check.checked).length+' 个平台'; results.replaceChildren(make('h2','预检结果'),make('p','内容或选择已更改，请重新预检。'));};
    for(const group of state.groups){
      const groupRows=state.channels.filter(c=>c.region===group.id);
      const box=panel(group.name+' · '+groupRows.length+' 个平台');
      const actions=make('div',null,'actions'); box.append(actions);
      button(actions,'全选'+group.name,()=>{for(const x of choices.filter(x=>x.channel.region===group.id))x.check.checked=true;invalidate();});
      button(actions,'清空'+group.name,()=>{for(const x of choices.filter(x=>x.channel.region===group.id))x.check.checked=false;invalidate();});
      for(const c of groupRows){
        const card=panel(c.name); const label=make('label');const check=make('input');check.type='checkbox';check.onchange=invalidate;
        label.append(check,make('span',' 选择 '+c.name));card.append(label);
        card.append(make('p',c.transport_status==='IMPLEMENTED'?'已有发布实现 · 本批量入口关闭':'发布接口尚未接入', 'badge'));
        card.append(make('p',c.owner_action));
        const accountLabel=make('label','目标账号');const account=make('select');account.append(new Option('请选择账号',''));
        for(const a of c.accounts)account.append(new Option(a.name+' · '+(a.connection_status||'待核实'),a.id));
        account.onchange=invalidate;accountLabel.append(account);card.append(accountLabel);
        const textLabel=make('label','该平台文案');const text=make('textarea');text.rows=3;text.maxLength=30000;text.oninput=invalidate;textLabel.append(text);card.append(textLabel);
        const idLabel=make('label','已审核文案 Content ID（可留空预检）');const contentId=make('input');contentId.type='number';contentId.min=1;contentId.oninput=invalidate;idLabel.append(contentId);card.append(idLabel);
        const assetsLabel=make('label','素材 Asset IDs（逗号分隔，来自共享素材库）');const assets=make('input');assets.oninput=invalidate;assetsLabel.append(assets);card.append(assetsLabel);
        card.append(make('p','素材类型：'+c.media_requirement));
        if(c.manage)button(card,'管理现有渠道',()=>location.assign(c.manage));
        const docs=make('a','平台官方入口 / 说明');docs.href=c.docs;docs.target='_blank';docs.rel='noopener noreferrer';card.append(docs);
        choices.push({channel:c,check,account,text,contentId,assets});box.append(card);
      }
      root.append(box);
    }
    const actions=panel('统一操作','完整自动适配与批量发布仍在开发。任何缺少账号、素材或审核的目标都会显示阻断原因。');
    button(actions,'PREVIEW ALL · 一键预检',async()=>{
      if(!selected())throw Error('请先选择 Campaign');
      const targets=choices.filter(x=>x.check.checked).map(x=>({platform:x.channel.id,content:x.text.value,
        social_account_id:Number(x.account.value)||null,content_id:Number(x.contentId.value)||null,
        asset_ids:x.assets.value.split(',').map(s=>s.trim()).filter(Boolean)}));
      if(!targets.length)throw Error('请至少选择一个平台');
      if(targets.some(t=>!t.content.trim()))throw Error('请为每个选中平台填写文案');
      const report=await api(base+'/preview',{campaign_id:selected(),targets,execution_mode:'TEST'});
      results.replaceChildren(make('h2','预检结果 · 未发布'));
      for(const r of report.results){const p=panel(r.name+' · '+r.status,r.blockers.join(' / '));p.append(make('p',r.content,'body'));results.append(p);}
    });
    const publish=button(actions,'PUBLISH · REAL 关闭',()=>{});publish.disabled=true;
    root.append(actions,results);
  } catch(e) {root.append(panel('发布中心暂不可用',e.message));}
};
