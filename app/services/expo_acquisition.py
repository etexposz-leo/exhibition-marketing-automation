"""Bounded public acquisition; reused legacy parser, no browser or credential access."""
import csv,hashlib,io,json,re,time
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser
from datetime import datetime,timezone
from bs4 import BeautifulSoup
from app.services import content_inspiration as public
from vendor.expocrawler.crawler.parser import ParserRegistry

FIELDS='trade_show show_url start_date end_date venue city state country company_name company_website booth_number contact_name contact_title business_email phone source_url source_type crawled_at confidence content_hash'.split()
class Manual(ValueError):pass
class Retry(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def fetch(url):
    # Every hop and robots request uses DNS pinning and rejects private addresses.
    current=public.normalize_url(url)
    for _ in range(4):
        u=urlsplit(current);status,headers,raw=public.request_once(f'https://{u.netloc}/robots.txt',256000)
        if status==200:
            rp=RobotFileParser();rp.parse(raw.decode('utf-8',errors='replace').splitlines())
            if not rp.can_fetch(public.AGENT,current):raise Manual('ROBOTS_DISALLOWED')
            delay=max(5,rp.crawl_delay(public.AGENT) or rp.crawl_delay('*') or 0)
            rate=rp.request_rate(public.AGENT) or rp.request_rate('*')
            if rate:delay=max(delay,rate.seconds/max(1,rate.requests))
            if delay>30:raise Manual('ROBOTS_DELAY_REQUIRES_MANUAL_SCHEDULING')
        elif status==404:delay=5
        else:raise Manual('ROBOTS_PERMISSION_UNAVAILABLE')
        time.sleep(delay)
        status,headers,raw=public.request_once(current)
        if status in (401,403,429,503):raise Manual('HTTP_'+str(status)+'_MANUAL_ACTION_REQUIRED')
        if status>=500:raise Retry('TEMPORARY_SOURCE_FAILURE')
        if status in (301,302,303,307,308):
            target=public.normalize_url(urljoin(current,headers.get('location','')))
            if urlsplit(target).hostname!=u.hostname:raise Manual('CROSS_DOMAIN_REDIRECT_REVIEW_REQUIRED')
            current=target;time.sleep(5);continue
        if status!=200:raise Manual('HTTP_'+str(status))
        if 'html' not in headers.get('content-type','').lower():raise Manual('HTML_SOURCE_REQUIRED')
        html=raw.decode('utf-8',errors='replace')
        if re.search(r'captcha|cf-chl-|verify you are human|access denied|type=["\x27]password|<title[^>]*>[^<]*(sign in|log in|登录)',html,re.I):raise Manual('LOGIN_OR_ANTIBOT_REVIEW_REQUIRED')
        return current,html
    raise Manual('REDIRECT_LIMIT')

def url(value):
    try:return public.normalize_url(value)
    except ValueError:return ''

def normalize(html,source,job):
    soup=BeautifulSoup(html,'html.parser');parsed=ParserRegistry().parse(source,html,'exhibitor')
    objects=[]
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            typ=value.get('@type',[]);typ=[typ] if isinstance(typ,str) else typ
            if set(typ)&{'Event','ExhibitionEvent','BusinessEvent','Organization','Corporation','LocalBusiness'}:objects.append(value)
            for key in ('@graph','subEvent','organizer','performer','exhibitor'):walk(value.get(key))
    for script in soup.select('script[type="application/ld+json"]'):
        try:walk(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):pass
    candidates=[];review_excerpt=None
    # Reviewed official igus event page: require its host, page, title, booth
    # heading and visible igus brand together; never infer identity from a title.
    if urlsplit(source).hostname=='www.igus.com' and urlsplit(source).path.rstrip('/')=='/company/pack-expo':
        heading=soup.find('h1');detail=soup.find('h2')
        title=heading.get_text(' ',strip=True) if heading else ''
        details=detail.get_text(' ',strip=True) if detail else ''
        year=re.fullmatch(r'PACK EXPO (20\d{2}) - Chicago',title)
        booth=re.fullmatch(r'Chicago, IL - October 18th - October 21st -\s+Booth\s+(\d+), North Hall',details)
        brand=any('igus' in str(a.get('alt','')).casefold() for a in soup.select('img[alt]'))
        if year and booth and brand:
            review_excerpt=title+' | '+details+' | '+' '.join(p.get_text(' ',strip=True) for p in soup.select('p') if 'booth '+booth[1] in p.get_text(' ',strip=True).lower())
            candidates.append(dict(company_name='igus',company_website='https://www.igus.com/',
                trade_show='PACK EXPO '+year[1],start_date=year[1]+'-10-18',end_date=year[1]+'-10-21',
                city='Chicago',state='IL',booth_number=booth[1]))
    for obj in objects:
        typ=obj.get('@type',[]);typ=[typ] if isinstance(typ,str) else typ
        r={};is_event=bool(set(typ)&{'Event','ExhibitionEvent','BusinessEvent'})
        if is_event:
            loc=obj.get('location') or {};loc=loc if isinstance(loc,dict) else {};address=loc.get('address') or {};address=address if isinstance(address,dict) else {}
            r.update(trade_show=obj.get('name',''),show_url=url(obj.get('url','')) or source,start_date=str(obj.get('startDate',''))[:10],end_date=str(obj.get('endDate',''))[:10],venue=loc.get('name',''),city=address.get('addressLocality',''),state=address.get('addressRegion',''),country=address.get('addressCountry',''))
        else:r.update(company_name=obj.get('name',''),company_website=url(obj.get('url','')),business_email=obj.get('email',''),phone=obj.get('telephone',''))
        candidates.append(r)
    # Label-based legacy exhibitor parser; never turn generic title into a company.
    explicit=soup.select_one('[itemprop=legalName], .company-name, .exhibitor-name')
    if explicit:
        parsed.company_name=explicit.get_text(' ',strip=True)
        candidates.append(dict(company_name=parsed.company_name,company_website=url(parsed.website),booth_number=parsed.booth_number,business_email=parsed.email,phone=parsed.phone,country=parsed.country))
    if not candidates and job['source_type'] in {'OFFICIAL_DIRECTORY','INDUSTRY_DIRECTORY'} and soup.title:
        candidates.append({})  # Resource provenance only, no invented company/show.
    text=(review_excerpt or soup.get_text(' ',strip=True))[:2000];result=[]
    for candidate in candidates:
        r={k:'' for k in FIELDS}
        r.update({k:str(v)[:2000] for k,v in candidate.items() if isinstance(v,(str,int,float))})
        for k in ('trade_show','show_url','start_date','end_date','venue','city','state','country'):
            if not r[k]:r[k]=job.get(k,'')
        r.update(source_url=source,source_type=job['source_type'],crawled_at=now(),confidence='EXTRACTED_REQUIRES_REVIEW')
        r['content_hash']=digest({k:r[k] for k in FIELDS if k not in {'crawled_at','content_hash','confidence'}})
        r['source_html_sha256']=hashlib.sha256(html.encode('utf-8')).hexdigest()
        r.update(id=r['content_hash'][:24],status='PENDING_REVIEW',source_excerpt=text,provenance=[source],reviewed_by=None)
        result.append(r)
    links=[]
    for a in soup.select('a[href]'):
        link=url(urljoin(source,a['href']))
        if link and urlsplit(link).hostname==urlsplit(source).hostname and re.search(r'exhibitor|company|directory|event|expo|show|resource|supplier',link,re.I) and not re.search(r'login|logout|signup|register|cart',link,re.I):links.append(link)
    return result,list(dict.fromkeys(links))

def keys(r):
    show=(r.get('trade_show','').strip().casefold(),r.get('start_date',''))
    # Scope company/email identity to a show occurrence, preserving repeat exhibitors.
    result={('hash',r['content_hash'])}
    if r.get('company_name'):
        if r.get('company_website'):result.add(('domain',show,urlsplit(r['company_website']).hostname.removeprefix('www.')))
        if r.get('booth_number'):result.add(('booth',show,r['company_name'].casefold(),r['booth_number'].casefold()))
        if r.get('business_email'):result.add(('email',show,r['business_email'].casefold()))
    elif all(show):result.add(('show',show))
    return result

def merge(records,new):
    added=0
    for r in new:
        match=next((x for x in records.values() if keys(x)&keys(r)),None)
        if match:
            match['provenance']=sorted(set(match['provenance']+r['provenance']))
            # Preserve reviewed fields; conflicting observations stay available separately.
            if r['content_hash']!=match['content_hash']:
                match.setdefault('observations',{})[r['content_hash']]={k:r[k] for k in FIELDS}
        else:records[r['id']]=r;added+=1
    return added

def export(records,fmt):
    if fmt=='json':return json.dumps(records,ensure_ascii=False,indent=2).encode(),'application/json'
    def safe(v):
        v=str(v or '')
        return "'"+v if v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n')) else v
    if fmt=='csv':
        f=io.StringIO();writer=csv.writer(f);writer.writerow(FIELDS)
        for r in records:writer.writerow([safe(r.get(k,'')) for k in FIELDS])
        return f.getvalue().encode('utf-8-sig'),'text/csv'
    if fmt=='xlsx':
        from openpyxl import Workbook
        w=Workbook();s=w.active;s.append(FIELDS)
        for r in records:s.append([safe(r.get(k,'')) for k in FIELDS])
        f=io.BytesIO();w.save(f);return f.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    raise ValueError('Unsupported format')
