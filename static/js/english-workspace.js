'use strict';
window.renderEnglishWorkspace=async function(root,ctx){
 const {api,make}=ctx,base='/api/marketing/modules/english';
 root.classList.add('english-host');
 const shell=make('div',null,'english-workspace'),status=make('p','正在读取学习工作区…','coach-status');status.setAttribute('role','status');root.append(shell);shell.append(status);
 let state,selected=null,cues=[],edits={},current=null,exercise=null,offset=0,loop=false,lastSaved=0;
 const command=(action,payload)=>api(base+'/command',{action,payload});
 const say=text=>{status.textContent=text};
 function btn(parent,text,fn){const b=make('button',text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){say(e.message)}finally{b.disabled=false}};parent.append(b);return b;}
 function input(parent,label,type='text',value=''){const l=make('label',label),e=make(type==='textarea'?'textarea':'input');if(type!=='textarea')e.type=type;e.value=value;e.setAttribute('aria-label',label);l.append(e);parent.append(l);return e;}
 function select(parent,label,options,value){const l=make('label',label),s=make('select');s.setAttribute('aria-label',label);for(const[v,t]of options){const o=make('option',t);o.value=v;s.append(o)}s.value=value;l.append(s);parent.append(l);return s;}
 function block(parent,title,cls=''){const b=make('section',null,cls);b.append(make('h2',title));parent.append(b);return b;}
 function download(name,data){const a=make('a'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 try{state=await api(base+'/workspace')}catch(e){say(e.message);return}
 if(!root.isConnected)return;
 const top=make('div',null,'coach-topbar');shell.prepend(top);
 const grid=make('div',null,'coach-grid');shell.append(grid);
 const left=make('div',null,'coach-left'),middle=make('div',null,'coach-middle'),right=make('div',null,'coach-right');grid.append(left,middle,right);
 const library=block(left,'视频列表'),search=input(library,'搜索视频'),videoList=make('div',null,'coach-list');library.append(videoList);
 const explain=block(left,'翻译与知识讲解'),explanation=make('p','选中字幕可保存词句、填写中文释义与笔记。AI 联网功能尚未启用。');explain.append(explanation);
 const selection=input(explain,'选中文字','textarea'),meaning=input(explain,'中文释义','textarea'),note=input(explain,'个人笔记','textarea');
 const itemKind=select(explain,'学习类型',[['word','单词'],['phrase','短语'],['sentence','句子'],['grammar','语法']],'sentence');
 btn(explain,'加入我的学习库',async()=>{if(!current)throw Error('请先选择字幕');await command('item',{subtitle_id:current.id,text:selection.value||textOf(current),meaning:meaning.value,note:note.value,kind:itemKind.value});await refreshState();say('已保存到当前用户学习库。')});
 const localItems=block(left,'我的学习库'),itemList=make('div',null,'coach-list');localItems.append(itemList);
 const playerBox=make('div',null,'coach-player'),player=make('video');player.controls=true;player.preload='metadata';player.setAttribute('aria-label','学习视频播放器');const overlay=make('div',null,'coach-overlay');playerBox.append(player,overlay);middle.append(playerBox);
 const controls=make('div',null,'coach-controls');middle.append(controls);
 btn(controls,'播放 / 暂停',()=>{if(!selected)throw Error('请先导入或选择视频');return player.paused?player.play():player.pause()});
 btn(controls,'后退 5 秒',()=>player.currentTime=Math.max(0,player.currentTime-5));btn(controls,'前进 5 秒',()=>player.currentTime=Math.min(Number.isFinite(player.duration)?player.duration:player.currentTime+5,player.currentTime+5));
 const adjacent=step=>{const list=englishCues(),i=list.findIndex(x=>x.id===current?.id);chooseCue(list[Math.max(0,Math.min(list.length-1,i+step))],true)};
 btn(controls,'上一句',()=>adjacent(-1));btn(controls,'下一句',()=>adjacent(1));
 const loopButton=btn(controls,'循环当前句：关',async()=>{loop=!loop;loopButton.textContent='循环当前句：'+(loop?'开':'关');await command('settings',{subtitle_loop_current:loop?1:0})});
 const rate=select(controls,'速度',[['0.5','0.5×'],['0.75','0.75×'],['1','1×'],['1.25','1.25×'],['1.5','1.5×'],['2','2×']],String(Number(state.settings.player_rate||1)));
 rate.onchange=()=>{player.playbackRate=Number(rate.value);command('settings',{player_rate:Number(rate.value)}).catch(e=>say(e.message))};player.playbackRate=Number(rate.value||1);
 const volume=input(controls,'音量','range',state.settings.player_volume||70);volume.min=0;volume.max=100;player.volume=Number(volume.value)/100;volume.onchange=()=>{player.volume=Number(volume.value)/100;command('settings',{player_volume:Number(volume.value)}).catch(e=>say(e.message))};
 const language=select(controls,'字幕',[['en','英文'],['zh','中文'],['both','双语']],state.settings.web_subtitle_language||'en');language.onchange=()=>{updateOverlay();command('settings',{web_subtitle_language:language.value}).catch(e=>say(e.message))};
 const position=select(controls,'字幕位置',[['bottom','底部'],['top','顶部']],state.settings.web_subtitle_position||'bottom');position.onchange=()=>{overlay.dataset.position=position.value;command('settings',{web_subtitle_position:position.value}).catch(e=>say(e.message))};overlay.dataset.position=position.value;
 const size=select(controls,'字幕大小',[['small','小'],['medium','中'],['large','大']],state.settings.web_subtitle_size||'large');size.onchange=()=>{overlay.dataset.size=size.value;command('settings',{web_subtitle_size:size.value}).catch(e=>say(e.message))};overlay.dataset.size=size.value;
 const timing=make('div',null,'coach-controls');middle.append(timing);offset=Number(state.settings.subtitle_offset_ms||0);const offsetInput=input(timing,'字幕偏移（毫秒）','number',offset);offsetInput.min=-600000;offsetInput.max=600000;
 async function setOffset(value){offset=Math.max(-600000,Math.min(600000,Number(value)||0));offsetInput.value=offset;await command('settings',{subtitle_offset_ms:offset});updateOverlay()}
 offsetInput.onchange=()=>setOffset(offsetInput.value).catch(e=>say(e.message));for(const n of [-500,-100,100,500])btn(timing,(n>0?'+':'')+n+'ms',()=>setOffset(offset+n));btn(timing,'恢复 0ms',()=>setOffset(0));
 loop=state.settings.subtitle_loop_current==='1';loopButton.textContent='循环当前句：'+(loop?'开':'关');
 const transcript=block(middle,'双语字幕'),source=make('p','尚未选择字幕','coach-source');transcript.append(source);
 const en=input(transcript,'当前英文字幕','textarea'),zh=input(transcript,'当前中文字幕','textarea');zh.readOnly=true;
 const subtitleActions=make('div',null,'coach-controls');transcript.append(subtitleActions);
 btn(subtitleActions,'复制英文',()=>navigator.clipboard.writeText(en.value));btn(subtitleActions,'复制中文',()=>navigator.clipboard.writeText(zh.value));btn(subtitleActions,'复制中英双语',()=>navigator.clipboard.writeText(en.value+'\n'+zh.value));
 btn(subtitleActions,'保存个人版本',async()=>{if(!current)throw Error('请先选择字幕');await command('subtitle',{id:current.id,text:en.value});edits[String(current.id)]=en.value;say('已保存个人版本，原字幕保留。');renderCues();updateOverlay()});
 btn(subtitleActions,'撤销未保存修改',()=>{if(current)en.value=textOf(current)});
 const cueSearch=input(transcript,'搜索字幕'),cueList=make('div',null,'coach-cues');transcript.append(cueList);cueSearch.oninput=renderCues;
 const ai=block(right,'AI 与来源'),network=make('p','外部 AI / 音频上传 / 自动 TED 下载：未启用。不会发送你的学习内容。','coach-boundary');ai.append(network);
 select(ai,'主模型',[['deepseek','DeepSeek'],['openai','OpenAI']],'deepseek');select(ai,'第二模型审核',[['none','未启用']],'none');
 const generate=btn(ai,'基于选中字幕生成练习',()=>{});generate.disabled=true;generate.title='需配置并批准外部 AI 服务后启用';
 const practice=block(right,'今日练习'),prompt=make('p','请从题库选择已审核题目。'),options=make('div');practice.append(prompt,options);const answer=input(practice,'输入你的答案');
 btn(practice,'提交答案',async()=>{if(!exercise)throw Error('请先选择已审核题目');const r=await command('answer',{id:exercise.id,answer:answer.value});say(r.is_correct===null?'已记录，开放式答案等待审核。':r.is_correct?'回答正确，复习进度已保存。':'已记录本次练习，查看答案后继续复习。');prompt.textContent=exercise.prompt+'\n答案：'+(r.answer||'待审核')+'\n'+(r.explanation||'');await refreshState()});
 btn(practice,'显示答案',async()=>{if(!exercise)throw Error('请先选择题目');const r=await command('show_answer',{id:exercise.id});prompt.textContent=exercise.prompt+'\n答案：'+(r.answer||'待审核')+'\n'+(r.explanation||'')});
 const bank=block(right,'题库审核'),filter=select(bank,'题库状态',[['approved','已审核题库'],['pending_ai_review','待 AI 审核'],['pending_user_confirmation','待用户确认'],['needs_check','需要检查'],['rejected','已拒绝']],'approved'),questions=make('div',null,'coach-list');bank.append(questions);filter.onchange=renderQuestions;
 const progress=block(right,'学习进度'),progressText=make('p');progress.append(progressText);
 const hidden=make('input');hidden.type='file';hidden.hidden=true;shell.append(hidden);
 async function pickUpload(kind){if(kind==='subtitle'&&!selected)throw Error('请先选择视频');hidden.accept=kind==='video'?'.mp4,.webm,.mp3,.mkv':'.srt,.vtt,.txt';hidden.value='';hidden.onchange=async()=>{const f=hidden.files[0];if(!f)return;say('正在本地导入…');try{const lang=kind==='subtitle'?importLanguage.value:'en';const r=await fetch(base+'/upload?kind='+kind+'&video_id='+(selected?.id||0)+'&language='+lang,{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'导入失败');await refreshState();if(kind==='video')await openVideo(value.id);else await openVideo(selected.id);say('已导入当前用户学习库。')}catch(e){say(e.message)}};hidden.click()}
 btn(top,'导入视频',()=>pickUpload('video'));btn(top,'导入字幕',()=>pickUpload('subtitle'));const importLanguage=select(top,'导入字幕语言',[['en','英文'],['zh','中文']],'en');
 btn(top,'导出学习记录',()=>download('english-learning-records.json',{history:state.history,items:state.items,export_limit:500}));
 btn(top,'学习设置',()=>{controls.scrollIntoView({block:'center',behavior:'smooth'});say('播放和字幕设置自动保存；AI 联网未启用。')});
 btn(top,'恢复默认布局',()=>{search.value='';cueSearch.value='';renderVideos();renderCues();shell.scrollIntoView({block:'start'})});
 function textOf(c){return edits[String(c.id)]??c.original_text}
 function englishCues(){return cues.filter(c=>c.language==='en')}
 function translation(c){return cues.filter(x=>x.language.startsWith('zh')&&x.start_ms<c.end_ms&&x.end_ms>c.start_ms).map(textOf).join('\n')}
 function chooseCue(c,seek){if(!c)return;current=c;en.value=textOf(c);zh.value=translation(c);selection.value=textOf(c);source.textContent='来源：'+c.source_provider+' · '+(edits[String(c.id)]!==undefined?'个人版本 / 原文保留':'原字幕');if(seek)player.currentTime=Math.max(0,(c.start_ms+offset)/1000);updateOverlay();for(const b of cueList.querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.id===String(c.id)))}
 function updateOverlay(){if(!current){overlay.textContent='';return}overlay.textContent=language.value==='zh'?translation(current):language.value==='both'?textOf(current)+'\n'+translation(current):textOf(current)}
 function renderCues(){cueList.replaceChildren();for(const c of englishCues().filter(x=>textOf(x).toLowerCase().includes(cueSearch.value.toLowerCase()))){const b=btn(cueList,Math.floor(c.start_ms/60000)+':'+String(Math.floor(c.start_ms/1000)%60).padStart(2,'0')+' '+textOf(c),()=>chooseCue(c,true));b.dataset.id=c.id;b.setAttribute('aria-pressed',String(c.id===current?.id))}if(!cueList.children.length)cueList.append(make('p','暂无匹配英文字幕，可导入 SRT / VTT / TXT。'))}
 function renderVideos(){videoList.replaceChildren();for(const v of state.videos.filter(x=>x.title.toLowerCase().includes(search.value.toLowerCase())))btn(videoList,v.title,()=>openVideo(v.id));if(!state.videos.length)videoList.append(make('p','导入本地视频，开始学习。'))}search.oninput=renderVideos;
 function renderItems(){itemList.replaceChildren();for(const x of state.items){const c=make('article');c.append(make('strong',x.english_text),make('p',x.chinese_meaning||''),make('small',x.item_type+' · 掌握度 '+Math.round(x.mastery*100)+'%'));btn(c,x.is_focus?'取消重点':'标记重点',async()=>{await command('focus',{id:x.id});await refreshState()});itemList.append(c)}progressText.textContent='词句 '+state.items.length+' · 练习记录 '+state.history.length+' · 今日复习 '+JSON.stringify(state.due)}
 function renderQuestions(){questions.replaceChildren();for(const x of state.exercises.filter(x=>x.reviewed_status===filter.value)){const c=make('article');c.append(make('p',x.prompt),make('small','来源：'+x.provider));if(x.reviewed_status==='approved')btn(c,'练习此题',()=>{exercise=x;prompt.textContent=x.prompt;answer.value='';options.replaceChildren();let list;try{list=JSON.parse(x.options_json||'[]')}catch{list=[]}if(Array.isArray(list))for(const option of list)btn(options,String(option),()=>answer.value=String(option))});else{btn(c,'接受选中题目',async()=>{await command('review',{id:x.id,status:'approved'});await refreshState()});btn(c,'拒绝选中题目',async()=>{await command('review',{id:x.id,status:'rejected'});await refreshState()})}questions.append(c)}if(!questions.children.length)questions.append(make('p','该分类暂无题目。'))}
 async function refreshState(){state=await api(base+'/workspace');if(!root.isConnected)return;renderVideos();renderItems();renderQuestions()}
 async function openVideo(id){const v=await api(base+'/videos/'+id);if(!root.isConnected)return;selected=v;cues=v.subtitles;edits=v.edits||{};current=null;player.src=base+'/videos/'+id+'/media';player.onloadedmetadata=()=>{player.currentTime=Math.max(0,(v.last_position_ms||0)/1000)};renderCues();chooseCue(englishCues()[0],false);say(v.title+' · 学习记录自动保存');}
 player.ontimeupdate=()=>{if(!selected||!root.isConnected)return;const now=player.currentTime*1000-offset;if(loop&&current&&now>=current.end_ms){player.currentTime=Math.max(0,(current.start_ms+offset)/1000);return}const c=englishCues().find(x=>x.start_ms<=now&&x.end_ms>now);if(c&&c.id!==current?.id)chooseCue(c,false);if(Date.now()-lastSaved>5000){lastSaved=Date.now();command('position',{id:selected.id,position_ms:Math.round(player.currentTime*1000)}).catch(e=>say(e.message))}};
 player.onerror=()=>say('此媒体无法由浏览器播放。支持的编码取决于浏览器；可导入 MP4/H.264 或 WebM。');
 en.onmouseup=()=>{const text=en.value.slice(en.selectionStart,en.selectionEnd);if(text){selection.value=text;player.pause()}};
 const observer=new MutationObserver(()=>{if(!shell.isConnected){player.pause();player.removeAttribute('src');player.load();observer.disconnect();root.classList.remove('english-host')}});observer.observe(root,{childList:true});
 renderVideos();renderItems();renderQuestions();say('学习工作区已就绪 · 当前用户独立保存 · 外部服务关闭');
};
