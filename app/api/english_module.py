"""Local companion launch and per-user read-only progress, no remote exposure."""
import os,subprocess,sqlite3,threading
import json, uuid
from urllib.parse import unquote
from pathlib import Path
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import module_access as access
from app.api.channel_workspace import origin
ROOT=Path(__file__).resolve().parents[2]
PYTHON=Path('F:/AI_Agents/TED_English_Learning/.venv/Scripts/python.exe')
router=APIRouter(prefix='/marketing/modules/english',tags=['English Coach companion'])
PROCESSES={};LOCK=threading.Lock()
BRIDGE=ROOT/'scripts/english_workspace.py'

def home(user):return ROOT/'data/modules/english'/str(int(user))

def workspace_call(user,action,payload=None):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','LOCALAPPDATA','APPDATA','USERPROFILE'}}
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    try:
        r=subprocess.run([str(PYTHON),'-B',str(BRIDGE),str(home(user))],input=json.dumps({'action':action,'payload':payload or {}}),text=True,encoding='utf-8',capture_output=True,env=env,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        value=json.loads(r.stdout)
    except (OSError,subprocess.TimeoutExpired,ValueError):
        raise HTTPException(503,'Learning workspace unavailable; check the local runtime')
    if r.returncode or not value.get('ok'):raise HTTPException(400,'Invalid request or missing local learning record')
    return value['result']

@router.get('/workspace')
def workspace(db:Session=Depends(get_db)):
    user=access.require(db,'ENGLISH_COACH_ACCESS')
    result=workspace_call(user,'state')
    if 'ENGLISH_COACH_HISTORY_VIEW' not in access.profile(db,user)['permissions']:result['history']=[]
    return {**result,'external_services_enabled':False,'integration_method':'EMBEDDED_WEB_WORKSPACE_EXISTING_COACH_ENGINE'}

@router.get('/videos/{video_id}')
def video(video_id:int,db:Session=Depends(get_db)):
    user=access.require(db,'ENGLISH_COACH_ACCESS')
    return {**workspace_call(user,'video',{'id':video_id}),**workspace_call(user,'personal_subtitles',{'id':video_id})}

@router.get('/videos/{video_id}/media')
def media(video_id:int,db:Session=Depends(get_db)):
    user=access.require(db,'ENGLISH_COACH_ACCESS')
    p=Path(workspace_call(user,'media_path',{'id':video_id})['path']).resolve()
    if not p.is_relative_to(home(user).resolve()) or not p.is_file():raise HTTPException(404,'Media unavailable')
    return FileResponse(p,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

class WorkspaceCommand(BaseModel):
    action:str=Field(max_length=40)
    payload:dict=Field(default_factory=dict)

@router.post('/command')
def command(value:WorkspaceCommand,request:Request,db:Session=Depends(get_db)):
    origin(request);user=access.require(db,'ENGLISH_COACH_ACCESS')
    if value.action not in {'position','subtitle','item','focus','review','answer','show_answer','settings'}:raise HTTPException(400,'Unsupported command')
    if len(json.dumps(value.payload))>50000:raise HTTPException(413,'Command too large')
    result=workspace_call(user,value.action,value.payload)
    if value.action not in {'position','settings','show_answer'}:access.audit(db,'ENGLISH_'+value.action.upper(),value.payload.get('id','current'))
    return result

@router.post('/upload')
async def upload(request:Request,kind:str='video',video_id:int=0,language:str='en',db:Session=Depends(get_db)):
    origin(request);user=access.require(db,'ENGLISH_COACH_ACCESS')
    name=unquote(request.headers.get('X-Filename','upload'))
    suffix=Path(name).suffix.lower()
    if kind not in {'video','subtitle'} or suffix not in ({'.mp4','.webm','.mp3','.mkv'} if kind=='video' else {'.srt','.vtt','.txt'}):raise HTTPException(400,'Unsupported upload type')
    if language not in {'en','zh'}:raise HTTPException(400,'Unsupported subtitle language')
    if kind=='subtitle':await run_in_threadpool(workspace_call,user,'video',{'id':video_id})
    folder=home(user)/'uploads';folder.mkdir(parents=True,exist_ok=True)
    # A generated name prevents browser-supplied paths from reaching the filesystem.
    p=folder/(uuid.uuid4().hex+suffix);limit=512*1024*1024 if kind=='video' else 4*1024*1024;size=0
    try:
        with p.open('xb') as f:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>limit:raise HTTPException(413,'Upload exceeds local size limit')
                f.write(chunk)
        if not size:raise HTTPException(400,'Empty upload')
        result=await run_in_threadpool(workspace_call,user,'import',{'path':str(p),'kind':kind,'video_id':video_id,'language':language,'title':Path(name).stem[:160]})
        access.audit(db,'ENGLISH_IMPORT',result.get('id',video_id))
        return result
    finally:
        # Only remove this request's generated staging file; the engine keeps its copy.
        if p.is_file():p.unlink()
def progress(user):
    p=home(user)/'data/app.db'
    if not p.exists():return {'initialized':False,'counts':{},'history':[],'vocabulary':[],'content':[]}
    db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['videos','learning_items','exercise_attempts','notes'] if t in tables}
        def rows(table,columns):
            if table not in tables:return []
            available={r[1] for r in db.execute('PRAGMA table_info('+table+')')};selected=[x for x in columns if x in available]
            return [dict(r) for r in db.execute('SELECT '+','.join(selected)+' FROM '+table+' ORDER BY id DESC LIMIT 50')]
        return {'initialized':True,'counts':counts,'history':rows('exercise_attempts',['id','created_at','is_correct','learning_item_id']),'vocabulary':rows('learning_items',['id','item_type','english_text','chinese_meaning','next_review_at','is_mastered','mastery']),'content':rows('videos',['id','title','created_at','last_position_ms','duration_ms'])}
    finally:db.close()

@router.get('')
def listing(db:Session=Depends(get_db)):
    user=access.require(db,'ENGLISH_COACH_ACCESS');profile=access.profile(db,user)
    result={'integration_method':'LOCAL_DESKTOP_COMPANION_WITH_EXISTING_SOURCE','user_id':user,'external_services_enabled':False,'runtime_available':PYTHON.is_file(),'features':['local media','subtitles','listening playback','vocabulary','reading','writing exercises','learning history','progress','settings'],'pronunciation_scoring':'NOT_CLAIMED','running':user in PROCESSES and PROCESSES[user].poll() is None,'data_directory':str(home(user))}
    if 'ENGLISH_COACH_HISTORY_VIEW' in profile['permissions']:result.update(progress(user))
    return result

@router.post('/launch')
def launch(request:Request,db:Session=Depends(get_db)):
    origin(request);user=access.require(db,'ENGLISH_COACH_ACCESS')
    if request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:raise HTTPException(403,'Desktop companion is local-only')
    if not PYTHON.is_file():raise HTTPException(409,'Restore the documented Python coach runtime first')
    with LOCK:
        if user in PROCESSES and PROCESSES[user].poll() is None:return {'running':True,'already_open':True}
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','LOCALAPPDATA','APPDATA','USERPROFILE'}}
        env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
        PROCESSES[user]=subprocess.Popen([str(PYTHON),'-X','utf8','-B',str(ROOT/'scripts/english_companion.py'),str(user)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        access.audit(db,'ENGLISH_COMPANION_OPENED',user)
    return {'running':True,'data_isolated_for_user':user,'external_services_enabled':False}
