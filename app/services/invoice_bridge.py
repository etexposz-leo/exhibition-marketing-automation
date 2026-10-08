"""Reuse the original parser and rules; isolated storage, no implicit .env loading."""
import importlib.util,sys,hashlib,email.policy,base64
from email import message_from_bytes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
_spec=importlib.util.spec_from_file_location('etexpo_vendor_invoice',ROOT/'vendor/invoice/invoice_downloader.py')
core=importlib.util.module_from_spec(_spec);sys.modules[_spec.name]=core;_spec.loader.exec_module(core)

def empty():return {'accounts':{},'matches':{},'history':[],'failures':[],'rules':{'keywords':list(core.DEFAULT_KEYWORDS),'extensions':sorted(core.DEFAULT_EXTENSIONS)}}

def preview(state,raw,account):
    if len(raw)>10_000_000:raise ValueError('Message too large')
    message=message_from_bytes(raw,policy=email.policy.default)
    if not core.contains_keyword(message,state['rules']['keywords']):return []
    mid=core.decode_mime(message.get('Message-ID')) or 'content:'+hashlib.sha256(raw).hexdigest()
    subject=core.decode_mime(message.get('Subject'));sender=core.decode_mime(message.get('From'))
    received=message.get('Date','');created=[]
    for filename,payload in core.iter_attachments(message,set(state['rules']['extensions'])):
        if len(payload)>5_000_000:continue
        sha=hashlib.sha256(payload).hexdigest();ident=hashlib.sha256((account+'|'+mid+'|'+filename+'|'+sha).encode()).hexdigest()
        duplicate=any(x['email_account']==account and (x['file_hash']==sha or (x['message_id']==mid and x['attachment_name']==filename)) for x in state['history'])
        # Preserve the original parser's supplier heuristic, explicitly unverified.
        item={'id':ident,'email_account':account,'message_id':mid,'sender':sender,'subject':subject,'received_at':received,'attachment_name':filename,'file_hash':sha,'vendor':core.identify_supplier(sender,subject,filename),'vendor_evidence':'ORIGINAL_TOOL_FILENAME_SENDER_HEURISTIC','invoice_number':None,'invoice_date':None,'amount':None,'currency':None,'local_file_path':None,'download_status':'DUPLICATE' if duplicate else 'PREVIEW','payload_b64':base64.b64encode(payload).decode()}
        if ident not in state['matches']:state['matches'][ident]=item
        elif duplicate:state['matches'][ident]['download_status']='DUPLICATE'
        created.append(ident)
    return created

def download(state,ident,user_id):
    item=state['matches'][ident]
    if any(x['email_account']==item['email_account'] and x['file_hash']==item['file_hash'] for x in state['history']):return False
    raw=base64.b64decode(item['payload_b64'],validate=True)
    if hashlib.sha256(raw).hexdigest()!=item['file_hash']:raise ValueError('Attachment integrity failed')
    root=ROOT/'data/modules/invoices'/str(int(user_id));root.mkdir(parents=True,exist_ok=True)
    # Deterministic opaque name plus safe original suffix; never use a supplied path.
    suffix=Path(item['attachment_name']).suffix.lower()
    if suffix not in core.DEFAULT_EXTENSIONS:raise ValueError('Unsupported attachment type')
    destination=root/(ident+suffix)
    try:
        with destination.open('xb') as f:f.write(raw)
    except FileExistsError:
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=item['file_hash']:raise ValueError('Existing file differs; preserved')
    item.update(download_status='DOWNLOADED',local_file_path=str(destination))
    state['history'].append({k:v for k,v in item.items() if k!='payload_b64'});return True
