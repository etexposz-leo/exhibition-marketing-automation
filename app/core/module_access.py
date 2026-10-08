"""Local unified module permissions stored in the existing encrypted store."""
from contextlib import contextmanager
from fastapi import HTTPException
from app.api import unified_marketing as records
from app.core.security import utcnow

PERMISSIONS={'CRAWLER_VIEW','CRAWLER_RUN','CRAWLER_CONFIGURE','CRAWLER_EXPORT','CRAWLER_APPROVE_RESULTS','MARKETING_ACCESS','INVOICE_VIEW','INVOICE_DOWNLOAD','INVOICE_ACCOUNT_MANAGE','INVOICE_RULE_MANAGE','ENGLISH_COACH_ACCESS','ENGLISH_COACH_HISTORY_VIEW','ENGLISH_COACH_ADMIN','USER_MANAGE'}
PERMISSIONS.add('QUOTE_ROBOT_ACCESS')
ROLES={'OWNER','ADMIN','STAFF','REVIEWER','READ_ONLY'}

def primary_owner():return int(records.config()['backlink_owner_id'])
@contextmanager
def target(db,user_id):
    previous=db.info.get('owner_id');db.info['owner_id']=int(user_id)
    try:yield
    finally:
        if previous is None:db.info.pop('owner_id',None)
        else:db.info['owner_id']=previous

def profile(db,user_id):
    with target(db,user_id):value=records.load_record(db,'module-access-v1',default={})
    base={'role':'READ_ONLY','permissions':[],'locked':False,'last_login':None,'session_version':0}
    base.update(value)
    if user_id==primary_owner():base.update(role='OWNER',permissions=sorted(PERMISSIONS))
    return base

def save_profile(db,user_id,value):
    with target(db,user_id):records.save_record(db,'module-access-v1',value)

def require(db,permission):
    user_id=db.info.get('owner_id')
    if not user_id:raise HTTPException(401,'Sign in required')
    p=profile(db,user_id)
    if p['locked'] or permission not in p['permissions']:raise HTTPException(403,'Module permission required')
    return user_id

def audit(db,action,object_id):
    value=records.load_record(db,'module-audit-v1',default=[])
    value.append({'at':utcnow().isoformat(),'action':action,'object_id':str(object_id),'actor':db.info['owner_id']})
    records.save_record(db,'module-audit-v1',value)
