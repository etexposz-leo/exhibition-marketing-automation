"""Explicit local Owner-managed accounts; no public signup activation."""
import threading
from fastapi import APIRouter,Depends,Request,HTTPException
from pydantic import BaseModel,Field,SecretStr
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import module_access as access
from app.core.auth import hash_password
from app.models.models import User
from app.api.channel_workspace import origin
router=APIRouter(prefix='/marketing/modules',tags=['unified local modules'])
LOCK=threading.RLock()

@router.get('/identity')
def identity(db:Session=Depends(get_db)):
    ident=db.info['owner_id'];p=access.profile(db,ident)
    if p['locked']:raise HTTPException(403,'Account locked')
    return {'user_id':ident,'is_primary_owner':ident==access.primary_owner(),**p,'permissions_catalog':sorted(access.PERMISSIONS)}

@router.get('/users')
def users(db:Session=Depends(get_db)):
    access.require(db,'USER_MANAGE')
    return {'roles':sorted(access.ROLES),'permissions':sorted(access.PERMISSIONS),'users':[{'id':u.id,'email':u.email,'display_name':u.username,'active':u.is_active,'created_at':u.created_at.isoformat(),**access.profile(db,u.id)} for u in db.query(User).order_by(User.id)]}

class Create(BaseModel):
    email:str=Field(min_length=5,max_length=254)
    display_name:str=Field(min_length=1,max_length=100)
    password:SecretStr
    role:str='READ_ONLY'
    permissions:list[str]=Field(default_factory=list)

def validate_role(db,role,permissions):
    if role not in access.ROLES or role=='OWNER' or set(permissions)-access.PERMISSIONS:raise HTTPException(400,'Invalid role/permission; primary Owner is fixed')
    actor=access.profile(db,db.info['owner_id'])
    if db.info['owner_id']!=access.primary_owner() and (role=='ADMIN' or 'USER_MANAGE' in permissions or set(permissions)-set(actor['permissions'])):raise HTTPException(403,'Only Owner may grant elevated access')

def password_hash(value):
    text=value.get_secret_value()
    if len(text)<16 or len(text.encode())>72:raise HTTPException(400,'Password must be 16+ characters and at most 72 UTF-8 bytes')
    return hash_password(text)

@router.post('/users')
def create(body:Create,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'USER_MANAGE');validate_role(db,body.role,body.permissions)
    from app.services.exhibitor_intelligence import email
    try:address=email(body.email)
    except ValueError:raise HTTPException(400,'Invalid email') from None
    with LOCK:
        if db.query(User).filter_by(email=address).first():raise HTTPException(409,'Account already exists')
        u=User(email=address,username=body.display_name,hashed_password=password_hash(body.password),is_active=True,is_demo=False);db.add(u);db.flush()
        access.save_profile(db,u.id,{'role':body.role,'permissions':sorted(set(body.permissions)),'locked':False,'session_version':1,'last_login':None})
        access.audit(db,'USER_CREATED',u.id)
    return {'id':u.id,'active':True}

class Update(BaseModel):
    role:str
    permissions:list[str]
    active:bool=True
    locked:bool=False
@router.post('/users/{ident}')
def update(ident:int,body:Update,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'USER_MANAGE')
    if ident==access.primary_owner() or ident==db.info['owner_id']:raise HTTPException(409,'Primary Owner and own access cannot be disabled or changed here')
    validate_role(db,body.role,body.permissions)
    u=db.query(User).filter_by(id=ident).first()
    if not u:raise HTTPException(404,'User not found')
    previous=access.profile(db,ident)
    if db.info['owner_id']!=access.primary_owner() and previous['role']=='ADMIN':raise HTTPException(403,'Owner controls Admin accounts')
    u.is_active=body.active;previous.update(role=body.role,permissions=sorted(set(body.permissions)),locked=body.locked,session_version=previous['session_version']+1)
    access.save_profile(db,ident,previous);access.audit(db,'USER_ACCESS_CHANGED',ident)
    return {'saved':True}

class Reset(BaseModel):password:SecretStr
@router.post('/users/{ident}/password')
def reset(ident:int,body:Reset,request:Request,db:Session=Depends(get_db)):
    origin(request);access.require(db,'USER_MANAGE')
    if ident==access.primary_owner():raise HTTPException(409,'Existing protected Owner credential is preserved')
    p=access.profile(db,ident)
    if db.info['owner_id']!=access.primary_owner() and p['role']=='ADMIN':raise HTTPException(403,'Owner controls Admin credentials')
    u=db.query(User).filter_by(id=ident).first()
    if not u:raise HTTPException(404,'User not found')
    u.hashed_password=password_hash(body.password);p['session_version']+=1;access.save_profile(db,ident,p);access.audit(db,'PASSWORD_RESET',ident)
    return {'saved':True}

@router.get('/audit')
def audit(db:Session=Depends(get_db)):
    access.require(db,'USER_MANAGE')
    from app.api.unified_marketing import load_record
    return {'events':load_record(db,'module-audit-v1',default=[])}
