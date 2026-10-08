"""Integrated Owner-only exhibitor prospecting and review, real SMTP disabled by default."""
import json,os,threading,uuid,subprocess
from datetime import datetime,timedelta,date
from pathlib import Path
from fastapi import APIRouter,Depends,Request,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import utcnow
from app.api import unified_marketing as work,channel_workspace as channels
from app.services import exhibitor_intelligence as intel,outreach_mail as mail,content_inspiration as public
from app.models.models import Campaign
from app.services.publishing import owned

router=APIRouter(prefix='/marketing/leads',tags=['exhibitor leads'])
LOCK=threading.RLock();SCOPE='exhibitor-workspace-v1'
STOP={'REPLIED','INTERESTED','QUOTE_REQUESTED','CUSTOMER','NOT_INTERESTED','DO_NOT_CONTACT'}

def empty():return {'companies':{},'contacts':{},'leads':{},'drafts':{},'sources':{},'events':[], 'settings':{'served_cities':[],'postal_address':'','quote_url':''},'templates':{k:{'id':k,'name':v[0],'subject':v[1],'body':v[2]} for k,v in intel.TEMPLATES.items()}}
def state(db):return work.load_record(db,SCOPE,default=None) or empty()
def save(db,s):work.save_record(db,SCOPE,s)
def event(s,kind,ident):s['events'].append({'id':uuid.uuid4().hex,'type':kind,'object_id':ident,'at':utcnow().isoformat()})
def row(s,table,ident):
 if ident not in s[table]:raise HTTPException(404,'Record not found')
 return s[table][ident]
def auth(request,db):channels.origin(request);work.backlink_owner(db)
def suppressed(keys,lead,contact):
 values={lead.get('domain','').lower(),contact.get('business_email','').lower(),contact.get('business_email','').split('@')[-1].lower()}
 return bool(values & keys) or lead.get('status')=='DO_NOT_CONTACT' or contact.get('no_solicitation')
def suppression():return {r['key'].lower() for r in work.backlink_call().get('suppression',[])}
def shared_stop(key,reason):return work.backlink_call('POST',{'key':key,'reason':reason},'/api/suppression')
def controls():return {'AUTO_LEAD_EMAIL_SEND':False,'AUTO_FOLLOWUP_SEND':False,'BULK_AUTO_SEND':False,'AUTO_BULK_SEND_ENABLED':False,'MANUAL_LEAD_SEND_ENABLED':os.getenv('LEAD_REAL_EMAIL_SEND_ENABLED','false')=='true'}
def mail_config(db):return work.load_record(db,'approved-outreach-smtp',default={})
def rev(value):return work.fingerprint(value)
def expect(value,revision):
 if not revision or rev(value)!=revision:raise HTTPException(409,'Record changed; refresh and review exact current version')
def joined(s,l):return {**l,'company':s['companies'][l['company_id']],'contact':s['contacts'][l['contact_id']],'intent':intel.score(l,s['settings']['served_cities']),'revision':rev(l)}
def due(s,lead):
 sent=sorted([d for d in s['drafts'].values() if d['lead_id']==lead['id'] and d['status']=='SENT'],key=lambda d:d['sent_at'])
 if not sent or lead['status'] in STOP or s['contacts'][lead['contact_id']].get('outreach_paused'):return None
 if any(d.get('reply_status') not in {None,'NONE'} or d.get('bounce_status')=='PERMANENT' for d in sent):return None
 followups=[d for d in s['drafts'].values() if d['lead_id']==lead['id'] and d.get('step',0)>0 and d['status']!='CANCELLED']
 if len(followups)>=2:return None
 step=len(followups)+1;at=datetime.fromisoformat(sent[0]['sent_at'])+timedelta(days=5 if step==1 else 12)
 return {'lead_id':lead['id'],'step':step,'due_at':at.isoformat(),'is_due':utcnow()>=at}

@router.get('')
def listing(db:Session=Depends(get_db)):
 work.backlink_owner(db);s=state(db)
 try:keys=suppression();blocked=None
 except HTTPException:keys=set();blocked='Shared suppression unavailable; review/send blocked'
 leads=[{**joined(s,l),'suppressed':suppressed(keys,l,s['contacts'][l['contact_id']])} for l in s['leads'].values()]
 drafts=[{**d,'revision':rev(d)} for d in s['drafts'].values()]
 def stats(ls,ds):return {'LEADS_DISCOVERED':len(ls),'QUALIFIED_LEADS':sum(x['status'] in {'QUALIFIED','PENDING_REVIEW','APPROVED_FOR_OUTREACH'} for x in ls),'EMAILS_READY':sum(x['status']=='READY_TO_SEND' for x in ds),'EMAILS_SENT':sum(x['status']=='SENT' for x in ds),'DELIVERED':sum(x.get('delivery_status')=='DELIVERED' for x in ds),'BOUNCED':sum(x.get('bounce_status')=='PERMANENT' for x in ds),'REPLIES':sum(x.get('reply_status') not in {None,'NONE'} for x in ds),'INTERESTED':sum(x['status']=='INTERESTED' for x in ls),'QUOTE_REQUESTS':sum(x['status']=='QUOTE_REQUESTED' for x in ls)}
 breakdown={}
 for field in ['trade_show','trade_show_city','venue','campaign_id','source_type']:
  breakdown[field]={str(v):stats([l for l in leads if l.get(field)==v],[d for d in drafts if d['lead_id'] in {l['id'] for l in leads if l.get(field)==v}]) for v in {l.get(field,'') for l in leads}}
 breakdown['template']={t:stats([l for l in leads if l['id'] in {d['lead_id'] for d in drafts if d['template_used']==t}],[d for d in drafts if d['template_used']==t]) for t in s['templates']}
 return {**s,'leads':leads,'drafts':drafts,'controls':controls(),'from_email':mail.FROM_EMAIL,'from_name':mail.FROM_NAME,'mail_configured':bool(mail_config(db)), 'suppression_error':blocked,'suppression':sorted(keys),'followups':[f for l in s['leads'].values() if not suppressed(keys,l,s['contacts'][l['contact_id']]) and (f:=due(s,l))],'analytics':stats(leads,drafts),'breakdown':breakdown,'statuses':intel.STATUSES,'source_types':intel.SOURCE_TYPES,'scoring_weights':intel.SIGNALS}

class Source(BaseModel):url:str=Field(max_length=2000)
@router.post('/inspect-source')
def inspect_source(body:Source,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 try:evidence=intel.inspect_public(body.url)
 except (ValueError,public.CollectionError):raise HTTPException(422,'Public source unavailable or disallowed; no guessed contacts created') from None
 with LOCK:
  s=state(db);ident=intel.ident(evidence['source_url']);evidence.update(id=ident,checked_at=utcnow().isoformat());s['sources'][ident]=evidence;save(db,s)
 return evidence

class Search(BaseModel):keyword:str=Field(min_length=3,max_length=120)
@router.post('/discover')
def discover(body:Search,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 # Search snippets are research candidates, never confirmed leads or inferred addresses.
 try:
  p=subprocess.run([str(work.ROOT/'.venv-content/Scripts/python.exe'),'-X','utf8','-B',str(work.ROOT/'scripts/discover_posts.py')],input=json.dumps({'query':body.keyword+' exhibitor official','limit':5}),capture_output=True,text=True,encoding='utf-8',timeout=55,env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP'}})
  result=json.loads(p.stdout)
 except Exception:raise HTTPException(503,'Public search unavailable; no leads fabricated') from None
 candidates=[]
 for item in result.get('results',[])[:5]:
  try:item['source_url']=public.normalize_url(item.get('source_url',''))
  except ValueError:continue
  candidates.append(item)
 with LOCK:
  s=state(db);s['last_search']={'keyword':body.keyword,'at':utcnow().isoformat(),'status':result.get('status'),'results':candidates};save(db,s)
 return s['last_search']

class Lead(BaseModel):
 company_name:str=Field(min_length=1,max_length=200)
 company_website:str=Field(max_length=1000)
 trade_show:str=Field(min_length=1,max_length=200)
 trade_show_date:str=''
 trade_show_city:str=Field(default='',max_length=100)
 venue:str=Field(default='',max_length=200)
 country:str=Field(default='',max_length=100)
 booth_number:str=Field(default='',max_length=80)
 contact_name:str=Field(default='',max_length=150)
 contact_title:str=Field(default='',max_length=150)
 business_email:str=Field(default='',max_length=254)
 phone:str=Field(default='',max_length=60)
 source_url:str=Field(max_length=2000)
 source_type:str
 source_date:str=''
 source_excerpt:str=Field(min_length=20,max_length=2000)
 email_source:str=Field(default='',max_length=2000)
 email_public_confirmed:bool=False
 email_evidence_id:str=''
 public_business_only:bool=False
 intent_signals:list[str]=Field(default_factory=list,max_length=8)
 engagement_evidence:str=Field(default='',max_length=1000)
 campaign_id:int|None=None
 notes:str=Field(default='',max_length=2000)
@router.post('/save')
def add_lead(body:Lead,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if not body.public_business_only:raise HTTPException(400,'Confirm public business provenance; private datasets are not allowed')
 if body.source_type not in intel.SOURCE_TYPES or set(body.intent_signals)-intel.SIGNALS.keys():raise HTTPException(400,'Invalid source or signal')
 if body.campaign_id:owned(db,Campaign,body.campaign_id,channels.owner(db))
 try:
  domain=intel.domain(body.company_website);address=intel.email(body.business_email);source=public.normalize_url(body.source_url)
  if body.email_source:public.normalize_url(body.email_source)
  for v in (body.trade_show_date,body.source_date):
   if v:date.fromisoformat(v)
 except ValueError:raise HTTPException(400,'Invalid domain, source URL, email or ISO date') from None
 with LOCK:
  s=state(db)
  if len(s['leads'])>=2000:raise HTTPException(409,'Local review capacity reached')
  company_id=intel.ident(domain);contact_id=intel.ident(company_id,address or body.contact_name or 'unknown', '' if address else body.contact_title)
  lead_id=intel.ident(company_id,body.trade_show,body.trade_show_date,body.booth_number,contact_id)
  if lead_id in s['leads']:return {'id':lead_id,'duplicate':True}
  evidence=s['sources'].get(body.email_evidence_id,{})
  observed=bool(address and address in evidence.get('public_business_emails',[]) and intel.domain(evidence['source_url'])==domain)
  confirmed=bool(address and body.email_public_confirmed and body.email_source)
  contact={'id':contact_id,'company_id':company_id,'contact_name':body.contact_name,'contact_title':body.contact_title,'business_email':address,'phone':body.phone,'email_source':evidence.get('source_url') if observed else body.email_source,'email_confidence':'PUBLICLY_OBSERVED_NOT_MAILBOX_VERIFIED' if observed else 'OWNER_ATTESTED_PUBLIC' if confirmed else 'UNVERIFIED','public_business_email':observed or confirmed,'email_status':'PUBLICLY_OBSERVED' if observed else 'OWNER_ATTESTED' if confirmed else 'UNVERIFIED','no_solicitation':bool(evidence.get('no_solicitation'))}
  if contact_id not in s['contacts']:s['contacts'][contact_id]=contact
  s['companies'].setdefault(company_id,{'id':company_id,'company_name':body.company_name,'company_website':body.company_website,'domain':domain})
  lead={**body.model_dump(exclude={'contact_name','contact_title','business_email','phone','email_source','email_public_confirmed','email_evidence_id','public_business_only','company_name','company_website'}),'id':lead_id,'company_id':company_id,'contact_id':contact_id,'domain':domain,'source_url':source,'status':'NEW','created_at':utcnow().isoformat()}
  s['leads'][lead_id]=lead;event(s,'LEAD_CREATED',lead_id);save(db,s)
 return {'id':lead_id,'duplicate':False}

class Transition(BaseModel):revision:str;status:str;note:str=Field(default='',max_length=2000)
@router.post('/{ident}/status')
def transition(ident:str,body:Transition,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if body.status not in intel.STATUSES:raise HTTPException(400,'Invalid pipeline state')
 if body.status=='CONTACTED':raise HTTPException(400,'CONTACTED is set only after a recorded send')
 with LOCK:
  s=state(db);l=row(s,'leads',ident);expect(l,body.revision);c=s['contacts'][l['contact_id']]
  if body.status=='DO_NOT_CONTACT':shared_stop(l['domain'],'Owner stopped exhibitor outreach')
  elif suppressed(suppression(),l,c):raise HTTPException(409,'Shared Do Not Contact is active')
  if body.status=='APPROVED_FOR_OUTREACH' and not c['public_business_email']:raise HTTPException(409,'Unverified email cannot be approved for outreach')
  l.update(status=body.status,notes=body.note,updated_at=utcnow().isoformat());event(s,'LEAD_'+body.status,ident);save(db,s)
 return {'saved':True}

class Settings(BaseModel):postal_address:str=Field(default='',max_length=500);quote_url:str=Field(default='',max_length=1000);served_cities:list[str]=Field(default_factory=list,max_length=30)
@router.post('/settings')
def settings(body:Settings,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if body.quote_url:public.normalize_url(body.quote_url)
 with LOCK:s=state(db);s['settings']=body.model_dump();save(db,s)
 return {'saved':True}
class Template(BaseModel):id:str;name:str=Field(max_length=150);subject:str=Field(min_length=1,max_length=200);body:str=Field(min_length=10,max_length=10000)
@router.post('/templates')
def template(body:Template,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if '\n' in body.subject or '\r' in body.subject:raise HTTPException(400,'Invalid subject')
 with LOCK:
  s=state(db);row(s,'templates',body.id);s['templates'][body.id]=body.model_dump();save(db,s)
 return {'saved':True}

class Generate(BaseModel):lead_ids:list[str]=Field(min_length=1,max_length=50);template_id:str='upcoming';step:int=Field(default=0,ge=0,le=2)
@router.post('/generate')
def generate(body:Generate,request:Request,db:Session=Depends(get_db)):
 auth(request,db);keys=suppression()
 with LOCK:
  s=state(db);t=row(s,'templates',body.template_id);created=[];skipped=[]
  for lid in dict.fromkeys(body.lead_ids):
   l=row(s,'leads',lid);c=s['contacts'][l['contact_id']];company=s['companies'][l['company_id']]
   if suppressed(keys,l,c) or l['status']=='NOT_INTERESTED':skipped.append(lid);continue
   if body.template_id=='booth_known' and not l['booth_number']:raise HTTPException(400,'Known booth template requires a booth number')
   city={'las_vegas':'las vegas','orlando':'orlando','chicago':'chicago'}.get(body.template_id)
   if city and l['trade_show_city'].lower()!=city:raise HTTPException(400,'City template does not match lead evidence')
   f=due(s,l)
   if body.step or body.template_id in {'followup','quote_followup'}:
    if not f or not f['is_due'] or body.step!=f['step']:raise HTTPException(409,'Follow-up is not due or has already been prepared')
    if body.template_id=='quote_followup' and not l.get('engagement_evidence'):raise HTTPException(409,'Quote reference required')
   elif any(d['lead_id']==lid and d.get('step',0)==0 and d['status']!='CANCELLED' for d in s['drafts'].values()):skipped.append(lid);continue
   values={'company':company['company_name'],'show':l['trade_show'],'city':l['trade_show_city'],'booth':l['booth_number'],'date':l['trade_show_date']}
   def render(text):
    for k,v in values.items():text=text.replace('{'+k+'}',v)
    return text
   intro=f"Hello {company['company_name']} team,\n\nI found your company in this public source regarding {l['trade_show']}: {l['source_url']}."
   if l['booth_number']:intro+=f" The source lists booth {l['booth_number']}."
   text=intro+'\n\n'+render(t['body'])
   if body.template_id=='quote_followup':text+='\nReference: '+l['engagement_evidence']
   if s['settings']['quote_url']:text+='\n\nRequest a quote: '+s['settings']['quote_url']
   text+='\n\nET EXPO / Leo\nleo@etexpous.com\n'+s['settings']['postal_address']+'\nIf this is not relevant, reply “unsubscribe” and we will stop contacting you.'
   subject=render(t['subject'])
   if '\r' in subject or '\n' in subject or len(subject)>200:raise HTTPException(400,'Rendered subject is invalid; correct source fields')
   did=uuid.uuid4().hex;draft={'id':did,'lead_id':lid,'from_email':mail.FROM_EMAIL,'from_name':mail.FROM_NAME,'to':c['business_email'],'subject':subject,'body':text.strip(),'template_used':body.template_id,'step':body.step,'status':'DRAFT','created_at':utcnow().isoformat(),'delivery_status':'NOT_SENT','bounce_status':'NONE','reply_status':'NONE','follow_up_at':None}
   s['drafts'][did]=draft;created.append(did);event(s,'DRAFT_CREATED',did)
  save(db,s);return {'created':created,'skipped':skipped,'sent':0}

class Edit(BaseModel):revision:str;to:str=Field(max_length=254);subject:str=Field(min_length=1,max_length=200);body:str=Field(min_length=10,max_length=20000)
@router.post('/drafts/{ident}/edit')
def edit(ident:str,body:Edit,request:Request,db:Session=Depends(get_db)):
 auth(request,db);address=intel.email(body.to)
 if '\n' in body.subject or '\r' in body.subject:raise HTTPException(400,'Subject cannot contain newlines')
 with LOCK:
  s=state(db);d=row(s,'drafts',ident);expect(d,body.revision)
  if d['status'] in {'SENT','SENDING','UNKNOWN'}:raise HTTPException(409,'Sent or uncertain submissions are immutable')
  d.update(to=address,subject=body.subject,body=body.body,status='DRAFT');event(s,'DRAFT_EDITED',ident);save(db,s)
 return {'saved':True}
class Review(BaseModel):revision:str;confirmed:bool=False

def eligible(s,d,keys):
 l=s['leads'][d['lead_id']];c=s['contacts'][l['contact_id']]
 if suppressed(keys,l,c) or d['to'].lower() in keys or d['to'].split('@')[-1].lower() in keys:raise HTTPException(409,'Recipient/company is suppressed')
 if l['status'] in STOP or c.get('outreach_paused'):raise HTTPException(409,'Contact replied or outreach stopped; no further send')
 if l['status'] not in {'APPROVED_FOR_OUTREACH','CONTACTED'}:raise HTTPException(409,'Approve lead for outreach first')
 if not c['public_business_email'] or c['email_status']=='UNVERIFIED' or d['to']!=c['business_email']:raise HTTPException(409,'Recipient must match the provenance-reviewed business email')
 if not s['settings']['postal_address']:raise HTTPException(409,'Configure the confirmed sender postal address before approval')
 if 'unsubscribe' not in d['body'].lower():raise HTTPException(409,'Include clear reply-to-unsubscribe instructions')

@router.post('/drafts/{ident}/approve')
def approve(ident:str,body:Review,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 with LOCK:
  s=state(db);d=row(s,'drafts',ident);expect(d,body.revision)
  if not body.confirmed or d['status'] not in {'DRAFT','PENDING_REVIEW'}:raise HTTPException(409,'Review exact draft before approval')
  eligible(s,d,suppression());d.update(status='READY_TO_SEND',approved_at=utcnow().isoformat());event(s,'DRAFT_APPROVED',ident);save(db,s)
 return {'status':'READY_TO_SEND','sent':False}

@router.post('/drafts/{ident}/send')
def send(ident:str,body:Review,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if not controls()['MANUAL_LEAD_SEND_ENABLED']:raise HTTPException(403,'Real mail disabled; Owner release approval and approved mail configuration required')
 with LOCK:
  s=state(db);d=row(s,'drafts',ident);expect(d,body.revision)
  if not body.confirmed or d['status']!='READY_TO_SEND':raise HTTPException(409,'Explicit Send confirmation of the approved version required')
  eligible(s,d,suppression());config=mail_config(db)
  if not config:raise HTTPException(409,'Approved ET EXPO mail configuration has not been connected')
  d.update(status='SENDING',message_id=f'<{uuid.uuid4().hex}@etexpous.com>',attempted_at=utcnow().isoformat());event(s,'SEND_ATTEMPT',ident);save(db,s)
  try:result=mail.submit(config,d)
  except Exception:
   d.update(status='UNKNOWN',delivery_status='UNKNOWN_REQUIRES_RECONCILIATION');event(s,'SEND_UNCERTAIN_NO_RETRY',ident);save(db,s)
   raise HTTPException(502,'Submission uncertain; automatic retry blocked. Reconcile with sender mailbox.') from None
  d.update(status='SENT',sent_at=utcnow().isoformat(),**result);l=s['leads'][d['lead_id']];l['status']='CONTACTED'
  if d['step']<2:d['follow_up_at']=(datetime.fromisoformat(d['sent_at'])+timedelta(days=5 if d['step']==0 else 7)).isoformat()
  event(s,'SMTP_ACCEPTED',ident);save(db,s)
  return {'message_id':d['message_id'],'delivery_status':d['delivery_status'],'sent_once':True}

class Response(BaseModel):revision:str;kind:str;text:str=Field(min_length=1,max_length=10000)
@router.post('/drafts/{ident}/response')
def response(ident:str,body:Response,request:Request,db:Session=Depends(get_db)):
 auth(request,db)
 if body.kind not in {'REPLIED','INTERESTED','QUOTE_REQUESTED','NOT_INTERESTED','OPT_OUT','PERMANENT_BOUNCE','DELIVERED'}:raise HTTPException(400,'Invalid response type')
 with LOCK:
  s=state(db);d=row(s,'drafts',ident);expect(d,body.revision)
  if d['status'] not in {'SENT','UNKNOWN'}:raise HTTPException(409,'No recorded submission to track')
  l=s['leads'][d['lead_id']]
  if body.kind in {'OPT_OUT','PERMANENT_BOUNCE'}:shared_stop(d['to'],'Exhibitor outreach '+body.kind)
  if body.kind=='DELIVERED':d['delivery_status']='DELIVERED'
  elif body.kind=='PERMANENT_BOUNCE':d['bounce_status']='PERMANENT';l['status']='DO_NOT_CONTACT'
  else:d['reply_status']=body.kind;l['status']='DO_NOT_CONTACT' if body.kind=='OPT_OUT' else body.kind
  if body.kind!='DELIVERED':
   s['contacts'][l['contact_id']]['outreach_paused']=True
   for other in s['drafts'].values():
    if s['leads'][other['lead_id']]['contact_id']==l['contact_id']:
     other['follow_up_at']=None
     if other['status'] in {'DRAFT','PENDING_REVIEW','READY_TO_SEND'}:other['status']='CANCELLED'
  d.setdefault('responses',[]).append({'kind':body.kind,'text':body.text,'at':utcnow().isoformat(),'source':'OWNER_IMPORTED_UNVERIFIED_PROVIDER_EVENT'})
  event(s,'RESPONSE_'+body.kind,ident);save(db,s)
 return {'saved':True}
