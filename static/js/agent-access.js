'use strict';
window.renderAgentAccess = async function(content,{api,make,panel,button,identity}) {
  if (!identity.is_primary_owner) { content.append(panel('AI 助手接入','仅 Owner 可以管理助手授权。')); return; }
  const note=panel('ChatGPT / Dot / Muse','先创建独立授权，再在对应助手中连接。创建授权不代表平台已连接。当前只开放活动查询、销售草稿和提交人工审核；无法批准、定时、发帖或发邮件。');
  content.append(note);
  const form=panel('创建可撤销授权');
  const select=make('select'); for(const name of ['ChatGPT','Dot','Muse','Other']) select.append(new Option(name,name));
  const label=make('label','助手 '); label.append(select); form.append(label);
  const hours=make('input'); hours.type='number';hours.min='1';hours.max='720';hours.value='24';
  const expiry=make('label','有效期（小时，最长 720） ');expiry.append(hours);form.append(expiry);
  const checks=[];
  for(const [scope,text] of [['marketing:read','读取活动和草稿'],['drafts:write','创建销售草稿'],['review:submit','提交人工审核']]) {
    const input=make('input');input.type='checkbox';input.checked=scope==='marketing:read';
    const item=make('label',text); item.prepend(input);form.append(item);checks.push([scope,input]);
  }
  const secret=make('input');secret.type='password';secret.readOnly=true;secret.autocomplete='off';secret.hidden=true;secret.setAttribute('aria-label','一次性助手授权令牌');
  const message=make('p');form.append(secret,message);
  button(form,'创建授权',async()=>{
    const result=await api('/api/marketing/agent-grants',{assistant:select.value,expires_hours:Number(hours.value),scopes:checks.filter(x=>x[1].checked).map(x=>x[0])});
    secret.value=result.token;secret.hidden=false;message.textContent='令牌只显示一次。请复制到助手的安全凭据设置，不要发送到聊天。';await refreshGrants();
  });
  button(form,'复制令牌',async()=>{if(secret.value){await navigator.clipboard.writeText(secret.value);message.textContent='已复制。配置完成后清除显示；剪贴板由你管理。';}});
  button(form,'清除令牌显示',()=>{secret.value='';secret.hidden=true;message.textContent='令牌显示已清除。';});
  content.append(form);const list=make('div');content.append(list);
  async function refreshGrants(){
    const result=await api('/api/marketing/agent-grants');list.replaceChildren();
    for(const g of result.grants){
      const card=panel(g.assistant,g.scopes.join(' / '));card.append(make('p',`${g.revoked?'已撤销':new Date(g.expires_at+'Z')<new Date()?'已过期':'授权有效'} · 到期 ${g.expires_at} UTC`));
      card.append(make('p','平台连接：尚未进行端到端验收'));
      if(!g.revoked)button(card,'撤销授权',async()=>{await api(`/api/marketing/agent-grants/${g.id}/revoke`,{});await refreshGrants();});
      button(card,'查看调用记录',async()=>{const r=await api(`/api/marketing/agent-grants/${g.id}/audit`);const pre=make('pre',JSON.stringify(r.events,null,2));card.append(pre);});list.append(card);
    }
  }
  try {await refreshGrants();} catch(error){content.append(panel('授权管理不可用',error.message));}
};
