"""Owner-only adapters to existing desktop data; never initialize/migrate originals."""
import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import threading
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

QUOTE = Path(r'F:\报价机器人ai')
INVOICE = Path(r'E:\Invoice')
CRAWLER = Path(r'F:\RUANJIAN\ExpoCrawler_Backup\ExpoCrawler_Backup\expo_crawler_source')
CRAWLER_RUNTIME = Path(r'F:\RUANJIAN\ExpoCrawler_Backup\ExpoCrawler_Backup\ExpoCrawler\_internal')
LOCK = threading.RLock()
SOURCES = {
    'email': (INVOICE/'_index/invoice_index.sqlite3', 'attachments', ['id','account_name','attachment_filename','saved_path','save_path','supplier','email_date','downloaded_at']),
    'marketplace': (INVOICE/'_index/marketplace_order_index.sqlite3', 'marketplace_orders', ['id','platform','order_number','order_date','preferred_document_type','saved_path','download_status','created_at']),
    'crawler': (CRAWLER_RUNTIME/'crawler.sqlite3', 'crawl_records', ['id','source_url','page_title','company_name','image_urls','video_urls','local_image_paths','local_video_paths','image_files','video_files','crawl_time']),
}

class Unavailable(Exception):
    pass

def read_rows(source, offset=0, limit=50):
    path, table, allowed = SOURCES[source]
    if not path.is_file():
        raise Unavailable('Original database unavailable; no new database created')
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            db.execute('PRAGMA query_only=ON')
            db.row_factory = sqlite3.Row
            columns = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
            selected = [x for x in allowed if x in columns]
            if 'id' not in selected:
                raise Unavailable('Original schema unsupported; no migration performed')
            total = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            rows = [dict(r) for r in db.execute(f'SELECT {",".join(selected)} FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))]
            return {'total': total, 'offset': offset, 'limit': limit, 'rows': rows, 'source': source, 'source_path': str(path), 'read_only': True}
    except sqlite3.Error:
        raise Unavailable('Original database busy or unreadable') from None

def quote_files():
    result = []
    for parent in [QUOTE/'output', QUOTE/'projects']:
        if not parent.is_dir():
            continue
        for p in parent.rglob('*'):
            if p.suffix.lower() not in {'.xlsx','.xlsm','.pdf'} or not p.is_file():
                continue
            resolved = p.resolve()
            if not resolved.is_relative_to(parent.resolve()):
                continue
            rel = p.relative_to(QUOTE).as_posix()
            result.append({'id': hashlib.sha256(rel.encode()).hexdigest(), 'name': p.name, 'relative_path': rel, 'bytes': p.stat().st_size})
            if len(result) >= 2000:
                return {'files': result, 'truncated': True, 'read_only': True}
    return {'files': result, 'truncated': False, 'read_only': True}

def quote_file(ident):
    for item in quote_files()['files']:
        if item['id'] == ident:
            p = (QUOTE/item['relative_path']).resolve()
            if any(p.is_relative_to((QUOTE/x).resolve()) for x in ('output','projects')):
                return p
    raise FileNotFoundError()

def invoice_file(source, ident):
    if source not in {'email','marketplace'}:
        raise FileNotFoundError()
    path, table, allowed = SOURCES[source]
    if not path.is_file():
        raise FileNotFoundError()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
        columns = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        cols = [x for x in ('saved_path','save_path') if x in columns]
        if not cols:
            raise FileNotFoundError()
        row = db.execute(f'SELECT {",".join(cols)} FROM {table} WHERE id=?', (ident,)).fetchone()
    for value in row or ():
        if not value:
            continue
        p = Path(value).resolve()
        if p.is_relative_to(INVOICE.resolve()) and p.suffix.lower() in {'.pdf','.png','.jpg','.jpeg','.xlsx','.csv','.txt'} and p.is_file():
            return p
    raise FileNotFoundError()

def original_module(name, path):
    """Compile from source without writing __pycache__ in the protected tree."""
    with LOCK:
        if not path.is_file():
            raise Unavailable('Original parser/exporter source missing')
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
            except Exception:
                sys.modules.pop(name, None)
                raise Unavailable('Original component unavailable') from None
        return sys.modules[name]

def parse_html(url, html, task):
    parser = original_module('etexpo_original_media_parser', CRAWLER/'crawler/parser.py')
    return asdict(parser.ParserRegistry().parse(url, html, task))

def export_crawler():
    """Keep original media filter/column contract; export in memory, no source writes."""
    exporter = original_module('etexpo_original_media_exporter', CRAWLER/'storage/excel_exporter.py')
    # Same original schema, fixed allowlist, bounded export; never invoke DB initializer.
    path, table, _ = SOURCES['crawler']
    if not path.is_file():
        raise Unavailable('Original database missing')
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            count = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            if count > 10000:
                raise Unavailable('Export exceeds 10000 rows; use original batch exporter')
            rows = [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY id')]
    except sqlite3.Error:
        raise Unavailable('Original database busy or unreadable') from None
    wb = exporter.Workbook()
    ws = wb.active
    ws.title = 'Expo Crawl Results'
    ws.append(exporter.HEADERS)
    for row in rows:
        if exporter._has_material(row):
            # Legacy DB stores material paths as image_files/video_files.
            row['local_image_paths'] = row.get('local_image_paths') or row.get('image_files','')
            row['local_video_paths'] = row.get('local_video_paths') or row.get('video_files','')
            ws.append([row.get(key,'') for key in exporter.HEADERS])
            for cell in ws[ws.max_row]:
                if cell.data_type == 'f':
                    cell.data_type = 's'  # Untrusted crawled strings are never spreadsheet formulas.
    output = io.BytesIO()
    wb.save(output)
    wb.close()
    return output.getvalue()
