"""Permission-protected invoice module, original scanner/parser reuse."""
import threading,imaplib,ssl,re,socket
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel,Field,SecretStr
from app.core.database import get_db
from app.core import module_access as access
from app.api import unified_marketing as records
from app.api.channel_workspace import origin
from app.services import invoice_bridge as bridge
router=APIRouter(prefix='/marketing/modules/invoices',tags=['invoice tool'])
LOCK=threading.RLock();SCOPE='invoice-module-v1'
class PublicIMAP(imaplib.IMAP4_SSL):
    def _create_socket(self,timeout):
        from app.services.content_inspiration import public_address
        address=public_address(self.host)
        sock=socket.create_connection((address,993),timeout)
        try:return self.ssl_context.wrap_socket(sock,server_hostname=self.host)
        except Exception:sock.close();raise
def state(db):return records.load_record(db,SCOPE,default=None) or bridge.empty()
def save(db,s):records.save_record(db,SCOPE,s)
def safe(item):return {k:v for k,v in item.items() if k not in {'password','username','payload_b64'}}

@router.get('')
def listing(db:Session=Depends(get_db)):
    access.require(db,'INVOICE_VIEW');s=state(db)
    return {'accounts':[safe(a) for a in s['accounts'].values()],'matches':[safe(a) for a in s['matches'].values()],'history':s['history'],'failures':s['failures'],'rules':s['rules'],'AUTO_INVOICE_SYNC_ENABLED':False,'original_tool':'Universal Email Invoice Downloader','legacy_history_location':'E:\\Invoice (preserved; not automatically imported)'}

class Account(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    host:str
    username:SecretStr
    password:SecretStr
@router.post('/accounts')
def account(body:Account,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'INVOICE_ACCOUNT_MANAGE')
    if not re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*\.)[A-Za-z]{2,}',body.host):raise HTTPException(400,'Use a public IMAP hostname')
    if not body.username.get_secret_value() or not body.password.get_secret_value():raise HTTPException(400,'Mailbox credentials required')
    with LOCK:
        s=state(db);s['accounts'][body.name]={'name':body.name,'host':body.host,'username':body.username.get_secret_value(),'password':body.password.get_secret_value()};save(db,s);access.audit(db,'INVOICE_ACCOUNT_SAVED',body.name)
    return {'saved':True}

class Rules(BaseModel):keywords:list[str]=Field(min_length=1,max_length=50);extensions:list[str]=Field(min_length=1,max_length=12)
@router.post('/rules')
def rules(body:Rules,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'INVOICE_RULE_MANAGE')
    if any(not x.strip() or len(x)>80 for x in body.keywords) or set(body.extensions)-set(bridge.core.DEFAULT_EXTENSIONS):raise HTTPException(400,'Invalid rules')
    with LOCK:s=state(db);s['rules']=body.model_dump();save(db,s);access.audit(db,'INVOICE_RULES_CHANGED','rules')
    return {'saved':True}

@router.post('/preview-eml')
async def preview(request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'INVOICE_VIEW')
    raw=bytearray()
    async for block in request.stream():
        raw.extend(block)
        if len(raw)>10_000_000:raise HTTPException(413,'Message exceeds 10 MB')
    with LOCK:
        s=state(db)
        try:ids=bridge.preview(s,bytes(raw),'Owner-uploaded EML')
        except Exception:raise HTTPException(400,'Cannot parse supplied message') from None
        save(db,s);access.audit(db,'INVOICE_LOCAL_PREVIEW',len(ids))
    return {'matches':len(ids),'mailbox_accessed':False}

class Scan(BaseModel):account:str;confirmed_mailbox_access:bool=False
@router.post('/scan')
def scan(body:Scan,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'INVOICE_ACCOUNT_MANAGE');access.require(db,'INVOICE_VIEW')
    if not body.confirmed_mailbox_access:raise HTTPException(409,'Explicit approval to read this mailbox is required')
    with LOCK:
        s=state(db);a=s['accounts'].get(body.account)
        if not a:raise HTTPException(404,'Mailbox configuration not found')
        found=0
        try:
            with PublicIMAP(a['host'],993,ssl_context=ssl.create_default_context(),timeout=20) as mailbox:
                mailbox.login(a['username'],a['password']);status,_=mailbox.select('INBOX',readonly=True)
                if status!='OK':raise ValueError()
                status,data=mailbox.search(None,'ALL')
                if status!='OK':raise ValueError()
                for ident in data[0].split()[-20:]:
                    status,parts=mailbox.fetch(ident,'(RFC822.SIZE)')
                    import re
                    sizes=re.findall(rb'RFC822.SIZE (\d+)',b' '.join(x for x in parts if isinstance(x,bytes)))
                    if not sizes or int(sizes[0])>10_000_000:continue
                    status,parts=mailbox.fetch(ident,'(BODY.PEEK[])')
                    if status!='OK':continue
                    raw=next((x[1] for x in parts if isinstance(x,tuple)),None)
                    if raw:found+=len(bridge.preview(s,raw,a['name']))
                mailbox.close()
        except Exception:
            s['failures'].append({'account':body.account,'status':'SCAN_FAILED','detail':'Provider error details withheld'});save(db,s)
            raise HTTPException(502,'Mailbox scan failed; check provider configuration locally') from None
        save(db,s);access.audit(db,'INVOICE_SCAN_PREVIEW',body.account)
    return {'matches':found,'downloaded':0,'readonly':True}

class Download(BaseModel):ids:list[str]=Field(min_length=1,max_length=50);confirmed:bool=False
@router.post('/download')
def download(body:Download,request:Request,db:Session=Depends(get_db)):
    origin(request);user=access.require(db,'INVOICE_DOWNLOAD')
    if not body.confirmed:raise HTTPException(409,'Confirm selected attachments')
    with LOCK:
        s=state(db)
        if any(x not in s['matches'] for x in body.ids):raise HTTPException(404,'Attachment not found')
        count=0
        for ident in dict.fromkeys(body.ids):
            try:count+=int(bridge.download(s,ident,user))
            except Exception:s['failures'].append({'attachment_id':ident,'status':'DOWNLOAD_FAILED','detail':'Local storage error; original preserved'})
        save(db,s);access.audit(db,'INVOICE_DOWNLOAD_SELECTED',count)
    return {'downloaded':count}

@router.get('/files/{ident}')
def file(ident:str,db:Session=Depends(get_db)):
    user=access.require(db,'INVOICE_DOWNLOAD');s=state(db);item=next((x for x in s['history'] if x['id']==ident),None)
    if not item:raise HTTPException(404,'File not found')
    from pathlib import Path
    p=Path(item['local_file_path']).resolve();root=(bridge.ROOT/'data/modules/invoices'/str(user)).resolve()
    if not p.is_relative_to(root) or not p.is_file():raise HTTPException(404,'File unavailable')
    return FileResponse(p,filename=bridge.core.clean_windows_name(item['attachment_name']),media_type='application/octet-stream',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
