"""Idempotent reviewed import to the existing backlink table, never a send queue."""
import hashlib,json,sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import HTTPException
from app.api import unified_marketing as work
from app.services import expo_acquisition as crawl

def handoff(record):
    root=Path(work.config()['backlink_root']);p=root/'PROJECT_SCOPE_GATE.json'
    if hashlib.sha256(p.read_bytes()).hexdigest().upper()!=(root/'PROJECT_SCOPE_GATE.sha256').read_text().strip().upper():raise HTTPException(503,'Backlink gate mismatch')
    gate=json.loads(p.read_text(encoding='utf-8-sig'))
    if gate['WEBSITE_TOUCHED']!='NO' or Path(gate['TARGET_PATH']).resolve()!=root.resolve():raise HTTPException(503,'Backlink scope invalid')
    source=crawl.public.normalize_url(record['source_url']);host=urlsplit(source).hostname
    if record['source_type'] not in {'OFFICIAL_DIRECTORY','INDUSTRY_DIRECTORY'}:raise HTTPException(409,'Review as a directory/resource opportunity first')
    ident=crawl.digest(source)[:24]
    db=sqlite3.connect((root/'state/history.sqlite3').as_uri()+'?mode=rw',uri=True)
    try:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT id FROM acquisition_opportunities WHERE source_url=?',(source,)).fetchone()
        if old:return {'opportunity_id':old[0],'duplicate':True}
        row={'id':ident,'domain':host,'source_url':source,'source_title':record['trade_show'] or record['company_name'] or host,'target_url':'','opportunity_type':'directory submission','category':'ExpoCrawler reviewed resource','contact_page':None,'submission_url':source,'authority_quality_signals':{'score':None,'industry_legitimacy':'REQUIRES_REVIEW','proprietary_authority':'NOT_AVAILABLE'},'relevance_score':None,'competitor_evidence':{},'recommended_outreach_method':'MANUAL_REVIEW','source_checked_at':record['crawled_at'],'snapshot':record['content_hash'],'source_validation':'CRAWLER_OWNER_REVIEWED','payment_required':'UNKNOWN','already_linked':False,'status':'DISCOVERED','last_action':None,'next_followup_at':None,'notes':'Reviewed ExpoCrawler '+record['id']+'; outreach approval remains separate','contact':None,'followup_count':0,'last_response':None,'do_not_contact':False,'city':record['city'],'industry':'Exhibitions','show':record['trade_show'],'campaign_id':None,'marketing_owner_id':work.config()['backlink_owner_id'],'provenance':record['provenance']}
        db.execute('INSERT INTO acquisition_opportunities(id,source_url,payload) VALUES(?,?,?)',(ident,source,json.dumps(row)))
        db.execute('INSERT INTO acquisition_events(object_id,action,at,payload) VALUES(?,?,?,?)',(ident,'CRAWLER_REVIEWED_IMPORT',crawl.now(),json.dumps({'record_id':record['id']})))
        db.commit();return {'opportunity_id':ident,'duplicate':False}
    finally:db.close()
