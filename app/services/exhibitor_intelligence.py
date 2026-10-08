"""Public exhibitor evidence and transparent scoring; no private data enrichment."""
import hashlib,re,html
from datetime import date
from urllib.parse import urlsplit,unquote
from app.services import content_inspiration as public

STATUSES=['NEW','RESEARCHED','QUALIFIED','PENDING_REVIEW','APPROVED_FOR_OUTREACH','CONTACTED','REPLIED','INTERESTED','QUOTE_REQUESTED','CUSTOMER','NOT_INTERESTED','DO_NOT_CONTACT']
SIGNALS={'official_exhibitor':35,'booth_published':15,'company_announces_exhibiting':25,'company_announces_attendance':10,'sponsor':15,'recent_show_activity':10,'vendor_information_request':25,'existing_inquiry':30}
SOURCE_TYPES=['OFFICIAL_EXHIBITOR_LIST','OFFICIAL_DIRECTORY','EXHIBITOR_SPONSOR_PAGE','COMPANY_ANNOUNCEMENT','COMPANY_EVENTS','PUBLIC_BUSINESS_CONTACT','INDUSTRY_DIRECTORY','AUTHORIZED_CRM']
TEMPLATES={
 'upcoming':('Upcoming show booth design/build','Planning for {show}','Would a discussion about your booth design or build requirements for {show} be useful?'),
 'las_vegas':('Las Vegas exhibitor','Your plans for {show} in Las Vegas','Would it be useful to discuss booth planning for your Las Vegas exhibition?'),
 'orlando':('Orlando exhibitor','Your plans for {show} in Orlando','Would it be useful to discuss your Orlando booth requirements?'),
 'chicago':('Chicago exhibitor','Your plans for {show} in Chicago','Would it be useful to discuss your Chicago exhibition plans?'),
 'logistics':('Booth shipping/logistics','Logistics planning for {show}','Are booth shipping or logistics topics you would like to discuss for this event?'),
 'installation':('Installation/dismantle','Installation planning for {show}','Would a discussion about installation and dismantle requirements be useful?'),
 'booth_known':('Known booth number','Planning for {show}, booth {booth}','Would a discussion about your requirements for booth {booth} be useful?'),
 'followup':('Follow-up email','Following up: {show}','Following up on our earlier email about {show}. Is this relevant to your current planning?'),
 'quote_followup':('Quote follow-up','Quote follow-up: {show}','Following up on the quote referenced below. Please let us know whether you have questions.')}

def ident(*parts):return hashlib.sha256('|'.join(str(x).strip().casefold() for x in parts).encode()).hexdigest()[:24]
def domain(url):
 u=public.normalize_url(url);h=urlsplit(u).hostname
 if not h or '.' not in h:raise ValueError('Company website must have a public domain')
 return h.removeprefix('www.')
def email(value):
 value=value.strip().lower()
 if value and not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',value):raise ValueError('Use one valid business email, no header newlines')
 return value

def score(lead,served_cities=()):
 reasons=[]
 for key in set(lead.get('intent_signals',[])):
  if key in SIGNALS:
   if key=='booth_published' and not lead.get('booth_number'):continue
   if key in {'existing_inquiry','vendor_information_request'} and not lead.get('engagement_evidence'):continue
   reasons.append({'signal':key,'points':SIGNALS[key],'evidence':'Owner-attested source'})
 try:days=(date.fromisoformat(lead.get('trade_show_date',''))-date.today()).days
 except (ValueError,TypeError):days=None
 if days is not None and 0<=days<=180:reasons.append({'signal':'upcoming_within_180_days','points':15,'days_until_show':days})
 if lead.get('country','').strip().upper() in {'US','USA','UNITED STATES'}:reasons.append({'signal':'US_show','points':10})
 if lead.get('trade_show_city','').casefold() in {c.casefold() for c in served_cities}:reasons.append({'signal':'Owner_confirmed_service_city','points':10})
 return {'score':min(100,sum(x['points'] for x in reasons)),'reasons':reasons,'formula':'sum explicit signal weights, capped at 100; not a buying probability'}

def inspect_public(url):
 url=public.normalize_url(url)
 # Reuse the bounded, DNS-pinned/robots-aware fetcher. No cookies or browser login.
 current=url
 for _ in range(4):
  public.robots_allowed(current);status,headers,raw=public.request_once(current)
  if status in {301,302,303,307,308}:
   from urllib.parse import urljoin
   current=public.normalize_url(urljoin(current,headers.get('location','')));continue
  if status!=200:raise ValueError('Public source unavailable')
  if 'html' not in headers.get('content-type','').lower():raise ValueError('Only public HTML sources are supported')
  from bs4 import BeautifulSoup
  soup=BeautifulSoup(raw,'html.parser')
  for x in soup(['script','style','noscript']):x.decompose()
  text=soup.get_text(' ',strip=True);source_domain=domain(current)
  addresses=set(re.findall(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',text,re.I))
  addresses.update(unquote(a['href'][7:].split('?')[0]) for a in soup.select('a[href^="mailto:"]'))
  verified=[]
  for value in addresses:
   try:value=email(value)
   except ValueError:continue
   if value and (value.split('@')[1]==source_domain or source_domain.endswith('.'+value.split('@')[1])):verified.append(value)
  return {'source_url':current,'source_type':'PUBLIC_BUSINESS_CONTACT','title':soup.title.get_text(strip=True)[:300] if soup.title else '', 'excerpt':text[:1600],'public_business_emails':sorted(verified),'observed_publication':True,'email_confidence':'PUBLICLY_OBSERVED_NOT_MAILBOX_VERIFIED','no_solicitation':bool(re.search(r'no solicitation|do not solicit|no unsolicited',text,re.I))}
 raise ValueError('Too many redirects')
