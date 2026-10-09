'use strict';
const statusNode = document.getElementById('status');
const connectButton = document.getElementById('connect');
async function tiktokRequest(path, options = {}) {
  const response = await fetch('/api/tiktok/' + path, {credentials: 'same-origin', ...options});
  let data;
  try { data = await response.json(); } catch (_) { throw new Error('服务器未返回有效响应，请刷新或重新登录。'); }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error('HTTP ' + response.status + ': ' + (typeof detail === 'string' ? detail :
      (detail?.message || '连接失败') + (detail?.fields ? '：' + detail.fields.join(', ') : '')));
  }
  return data;
}
connectButton.addEventListener('click', async () => {
  connectButton.disabled = true;
  statusNode.textContent = '正在启动 TikTok 授权…';
  try {
    const data = await tiktokRequest('oauth/start', {method: 'POST'});
    const url = new URL(data.authorization_url);
    if (url.origin !== 'https://www.tiktok.com' || url.pathname !== '/v2/auth/authorize/') throw new Error('授权地址校验失败');
    window.location.assign(url.href);
  } catch (error) { statusNode.textContent = error.message; connectButton.disabled = false; }
});
tiktokRequest('accounts').then(data => {
  statusNode.textContent = data.accounts.length ? '已授权基本资料；昵称不等于 @用户名，请核对授权账号。REAL 发布关闭。' : '尚未连接，请在 TikTok 授权页选择 @etexpoinc。';
  for (const account of data.accounts) {
    const row = document.createElement('li');
    row.textContent = account.display_name + ' — ' + account.external_id + ' — ' + account.connection_status;
    document.getElementById('accounts').appendChild(row);
  }
}).catch(error => { statusNode.textContent = error.message; });
