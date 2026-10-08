'use strict';
window.renderOriginalSoftware=async function(root,ctx,module){
 if(ctx.identity?.role!=='OWNER')return;
 const{api,make,panel,button}=ctx,base='/api/marketing/original',box=panel('原软件能力接入','读取现有文件和历史，保留原数据；不会启动邮箱、采集或报价任务。');root.append(box);
 const status=make('p','读取中…');status.setAttribute('role','status');box.append(status);
 try{
  if(module==='quote'){
   const s=await api(base+'/quote/files');status.textContent='原项目／输出文件：'+s.files.length+(s.truncated?'（已达显示上限）':'');
   const search=make('input');search.type='search';search.placeholder='筛选原项目或文件';search.setAttribute('aria-label','筛选原报价文件');box.append(search);
   const list=make('div');box.append(list);
   const draw=()=>{list.replaceChildren();for(const f of s.files.filter(f=>f.relative_path.toLowerCase().includes(search.value.toLowerCase()))){const row=make('p'),a=make('a',f.relative_path);a.href=base+'/quote/files/'+f.id;a.download=f.name;row.append(a);list.append(row)}};search.oninput=draw;draw();
  }else{
   let source=module==='invoice'?'email':'crawler',offset=0;
   const nav=make('div',null,'actions'),list=make('div');box.append(nav,list);
   const load=async()=>{try{const url=source==='crawler'?'/crawler/records':'/invoices/'+source;const s=await api(base+url+'?offset='+offset+'&limit=25');status.textContent=source+' · 原数据库共 '+s.total+' 条 · 当前偏移 '+offset;list.replaceChildren();for(const item of s.rows){const row=panel(item.attachment_filename||item.page_title||item.order_number||String(item.id));const details=make('pre',JSON.stringify(item,null,2));details.style.whiteSpace='pre-wrap';details.style.overflowWrap='anywhere';row.append(details);if(module==='invoice'&&(item.saved_path||item.save_path)){const a=make('a','下载已有本地文件');a.href=base+'/invoices/'+source+'/files/'+item.id;row.append(a)}list.append(row)}next.disabled=offset+25>=s.total;previous.disabled=offset===0}catch(e){status.textContent=e.message;list.replaceChildren()}};
   if(module==='invoice')for(const [key,label]of [['email','邮件附件历史'],['marketplace','商城文档历史']])button(nav,label,async()=>{source=key;offset=0;await load()});
   const previous=button(nav,'上一页',async()=>{offset=Math.max(0,offset-25);await load()}),next=button(nav,'下一页',async()=>{offset+=25;await load()});await load();
   if(module==='crawler'){
    const a=make('a','导出原素材记录 Excel');a.href=base+'/crawler/export.xlsx';box.append(a);
    const f=make('form'),heading=make('h3','原解析器：离线 HTML 预览');box.append(heading,f);
    for(const[name,label,type]of [['source_url','来源 URL（只作解析基准，不联网）','url'],['task','采集任务说明','text'],['html','已保存的公开页面 HTML','textarea']]){const l=make('label',label),input=make(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.name=name;input.required=name!=='task';if(name==='html'){input.maxLength=500000;input.rows=6}l.append(input);f.append(l)}
    const submit=make('button','离线解析');submit.type='submit';f.append(submit);const result=make('pre');result.style.whiteSpace='pre-wrap';result.style.overflowWrap='anywhere';box.append(result);f.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{const s=await api(base+'/crawler/parse',Object.fromEntries(new FormData(f)));result.textContent=JSON.stringify(s,null,2)}catch(err){result.textContent=err.message}finally{submit.disabled=false}};
   }
  }
 }catch(e){status.textContent=e.message}
};
