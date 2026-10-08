'use strict';
const el = id => document.getElementById(id);
let realEnabled = false;
let connectedAccounts = [];
function showLifecycle() {
    const a = connectedAccounts.find(a => String(a.id) === String(el('account').value));
    el('refresh').disabled = !a || !a.refresh_available;
    el('connection').textContent = a ? a.lifecycle_message : 'No connected account. Connect with OAuth.';
    el('connect').textContent = a && ['TOKEN_EXPIRING','REAUTH_REQUIRED'].includes(a.token_status) ? 'Reconnect with LinkedIn OAuth' : 'Connect with LinkedIn OAuth';
}
async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request rejected');
    return data;
}
async function load() {
    const data = await api('/api/linkedin/accounts');
    realEnabled = data.real_enabled;
    connectedAccounts = data.accounts;
    el('gate').textContent = realEnabled ? 'REAL is enabled by local operator configuration. Confirm the selected identity and text before submitting.' : 'REAL is locked. Separate owner authorization is required before the first external post.';
    el('account').replaceChildren();
    for (const a of data.accounts) {
        const option = document.createElement('option');option.value=a.id;
        option.textContent=`${a.display_name} — ${a.external_id} — ${a.token_status || a.connection_status}`;
        el('account').append(option);
    }
    showLifecycle();
}
async function guarded(action) {try {await action();} catch(e) {el('result').textContent=e.message;}}
el('connect').onclick=()=>guarded(async()=>{const data=await api('/api/linkedin/oauth/start',{});location.assign(data.authorization_url);});
el('account').onchange=showLifecycle;
el('refresh').onclick=()=>guarded(async()=>{await api(`/api/linkedin/accounts/${el('account').value}/refresh`,{});await load();});
el('disconnect').onclick=()=>guarded(async()=>{const data=await api(`/api/linkedin/accounts/${el('account').value}/disconnect`,{});el('connection').textContent=data.message;await load();});
el('timezone').textContent='Schedule timezone: '+Intl.DateTimeFormat().resolvedOptions().timeZone;
async function stableKey(payload) {
    const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));
    const signature=Array.from(new Uint8Array(digest)).map(x=>x.toString(16).padStart(2,'0')).join('');
    const storageKey='linkedin-job-'+signature;
    let key=sessionStorage.getItem(storageKey);
    if (!key) {key=crypto.randomUUID();sessionStorage.setItem(storageKey,key);}
    return key;
}
el('publish').onclick=()=>guarded(async()=>{
    const mode=el('mode').value;
    if(mode==='REAL' && !realEnabled) throw new Error('REAL is locked; explicit owner authorization is still required.');
    const account=Number(el('account').value)||null;
    if(mode==='REAL' && !account) throw new Error('Choose a connected LinkedIn account.');
    const payload={platform:'linkedin',content:el('content').value,social_account_id:account,execution_mode:mode};
    const when=el('when').value;
    if(when){payload.scheduled_at=new Date(when).toISOString();payload.timezone=Intl.DateTimeFormat().resolvedOptions().timeZone;}
    payload.idempotency_key=await stableKey(payload);
    if(mode==='REAL' && !window.confirm('Publish this exact text as the selected LinkedIn identity'+(when?' at the scheduled time':' now')+'?')) return;
    el('publish').disabled=true;
    try {const data=await api(when?'/api/schedule':'/api/publish-now',payload);el('result').textContent=JSON.stringify(data,null,2);}
    finally {el('publish').disabled=false;}
});
guarded(load);
