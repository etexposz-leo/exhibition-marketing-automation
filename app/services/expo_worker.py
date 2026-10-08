"""Service-owned, single-instance durable crawler execution. No browser polling needed."""
import os,threading,time
from pathlib import Path
from starlette.requests import Request
from app.core import module_access as access
from app.models.models import CredentialMetadata,User

class ProcessLease:
    def __init__(self,path):self.path=Path(path);self.file=None
    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        f=self.path.open('a+b')
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,IOError):f.close();return False
        self.file=f;return True
    def release(self):
        if self.file:self.file.close();self.file=None

class CrawlerWorker:
    def __init__(self,factory,lock_path,interval=2):
        self.factory=factory;self.lease=ProcessLease(lock_path);self.interval=interval
        self.stop_event=threading.Event();self.thread=None;self.last_tick=None;self.last_error=None;self.cursor=0
    def start(self):
        if self.thread and self.thread.is_alive():return True
        if not self.lease.acquire():return False
        self.stop_event.clear();self.thread=threading.Thread(target=self.run,name='expocrawler-worker',daemon=True);self.thread.start();return True
    def status(self):return {'running':bool(self.thread and self.thread.is_alive()),'last_tick':self.last_tick,'last_error':self.last_error}
    def stop(self,timeout=150):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout)
        return not (self.thread and self.thread.is_alive())
    def run(self):
        try:
            while not self.stop_event.is_set():
                try:self.tick();self.last_error=None
                except Exception:self.last_error='WORKER_TICK_FAILED' # Never log source/credentials or exception payload.
                self.last_tick=time.time();self.stop_event.wait(self.interval)
        finally:self.lease.release()
    def tick(self):
        from app.api import expo_module as module
        with self.factory() as db:
            ids=[x[0] for x in db.query(CredentialMetadata.user_id).filter(CredentialMetadata.scope==module.SCOPE).distinct().all()]
        due=[]
        for user_id in ids:
            with self.factory() as db:
                db.info['owner_id']=user_id
                with module.LOCK:
                    user=db.query(User).filter(User.id==user_id).first();profile=access.profile(db,user_id);s=module.state(db)
                    permitted=user and user.is_active and not profile['locked'] and 'CRAWLER_RUN' in profile['permissions']
                    if not permitted:
                        changed=False
                        for j in s['jobs'].values():
                            if j['status']=='RUNNING':j.update(status='PAUSED',last_error='ACCOUNT_OR_CRAWLER_PERMISSION_REVOKED');changed=True
                        if changed:module.save(db,s)
                        continue
                    due.extend((user_id,j['id']) for j in s['jobs'].values() if j['status']=='RUNNING' and j['next_request_at']<=time.time())
        if due and not self.stop_event.is_set():
            # Round-robin eligible jobs; bounded single network request chain at a time.
            user_id,ident=due[self.cursor%len(due)];self.cursor+=1
            with self.factory() as db:
                db.info['owner_id']=user_id
                request=Request({'type':'http','method':'POST','path':'/internal/crawler-worker','headers':[(b'origin',os.getenv('CHANNEL_WORKSPACE_ORIGIN','https://localhost:18421').encode())]})
                try:module.step(ident,request,db)
                except Exception:
                    # A concurrent pause/cancel/revoke may invalidate a previously eligible job.
                    db.rollback();raise

WORKER=None
def start_local_worker(factory):
    global WORKER
    if os.getenv('EXPO_CRAWLER_WORKER_ENABLED')!='true':return False
    if os.getenv('MARKETING_LOCAL_AUTH')!='true' or os.getenv('ENVIRONMENT')=='production':raise RuntimeError('Crawler worker requires local acceptance mode')
    root=Path(__file__).resolve().parents[2]
    WORKER=CrawlerWorker(factory,root/'data/modules/crawler/runtime/worker.lock')
    if not WORKER.start():raise RuntimeError('A crawler service already owns this workspace')
    print('EXPOCRAWLER_BACKGROUND_WORKER=STARTED',flush=True);return True

def status():return WORKER.status() if WORKER else {'running':False,'last_tick':None,'last_error':None}
def stop_local_worker():
    if WORKER and not WORKER.stop():raise RuntimeError('Crawler worker did not stop within bounded shutdown')
