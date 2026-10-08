"""Capability integration, not desktop remoting. Reuses existing auth and port."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import module_access as access
from app.api.channel_workspace import origin
from app.services import original_software as service

router = APIRouter(prefix='/marketing/original', tags=['Original software integration'])

def owner(db, permission):
    if access.require(db, permission) != access.primary_owner():
        raise HTTPException(403, 'Original shared desktop data is Owner-only')

def invoke(fn, *args):
    try:
        return fn(*args)
    except service.Unavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except (OSError, ValueError):
        raise HTTPException(503, 'Original data unavailable') from None

@router.get('/quote/files')
def quote_files(db: Session = Depends(get_db)):
    owner(db, 'QUOTE_ROBOT_ACCESS')
    return invoke(service.quote_files)

@router.get('/quote/files/{ident}')
def quote_file(ident: str, db: Session = Depends(get_db)):
    owner(db, 'QUOTE_ROBOT_ACCESS')
    try:
        path = service.quote_file(ident)
    except FileNotFoundError:
        raise HTTPException(404, 'Original output not found') from None
    return FileResponse(path, filename=path.name, headers={'Cache-Control':'private, no-store'})

@router.get('/invoices/{source}')
def invoices(source: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    owner(db, 'INVOICE_VIEW')
    if source not in {'email','marketplace'}:
        raise HTTPException(404, 'Unknown history source')
    return invoke(service.read_rows, source, offset, limit)

@router.get('/invoices/{source}/files/{ident}')
def invoice_file(source: str, ident: int, db: Session = Depends(get_db)):
    owner(db, 'INVOICE_DOWNLOAD')
    try:
        path = service.invoice_file(source, ident)
    except (FileNotFoundError, OSError, service.sqlite3.Error):
        raise HTTPException(404, 'Original invoice unavailable') from None
    return FileResponse(path, filename=path.name, headers={'Cache-Control':'private, no-store'})

@router.get('/crawler/records')
def crawler(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    owner(db, 'CRAWLER_VIEW')
    return invoke(service.read_rows, 'crawler', offset, limit)

class Preview(BaseModel):
    source_url: HttpUrl
    html: str = Field(min_length=1, max_length=500000)
    task: str = Field(default='', max_length=2000)

@router.post('/crawler/parse')
def parse(body: Preview, request: Request, db: Session = Depends(get_db)):
    origin(request)
    owner(db, 'CRAWLER_CONFIGURE')
    data = invoke(service.parse_html, str(body.source_url), body.html, body.task)
    return {'parsed': data, 'network_requested': False, 'original_database_modified': False}

@router.get('/crawler/export.xlsx')
def export(db: Session = Depends(get_db)):
    owner(db, 'CRAWLER_EXPORT')
    data = invoke(service.export_crawler)
    return Response(data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename="original-crawler.xlsx"','Cache-Control':'private, no-store'})
