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
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error(`Server returned an unreadable response (HTTP ${response.status}). Please retry or contact the administrator.`); }
    if (!response.ok) {
        if (response.status === 401) throw new Error('Your login session has expired. Sign in again before connecting LinkedIn.');
        const detail = data.detail;
        const message = typeof detail === 'string' ? detail :
            detail && typeof detail.message === 'string' ? detail.message +
            (Array.isArray(detail.fields) ? ' Required configuration: ' + detail.fields.join(', ') : '') : 'Request rejected';
        throw new Error(`HTTP ${response.status}: ${message}`);
    }
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
el('connect').onclick=async()=>{
    const button=el('connect'), status=el('oauth-status');
    if(button.disabled) return;
    button.disabled=true; status.textContent='Starting LinkedIn authorization…';
    try {
        const data=await api('/api/linkedin/oauth/start',{});
        const url=new URL(data.authorization_url);
        if(url.origin!=='https://www.linkedin.com' || url.pathname!=='/oauth/v2/authorization') throw new Error('Server returned an invalid LinkedIn authorization URL.');
        status.textContent='Opening LinkedIn. Complete login and consent on LinkedIn.';
        location.assign(url.href);
    } catch(e) {status.textContent=e.message;el('result').textContent=e.message;}
    finally {button.disabled=false;}
};
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
