from urllib.parse import parse_qs, urlsplit
import pytest
from tests.test_phase1 import storage, client, no_network
from app.api import tiktok_routes as yt
from app.core.credentials import CredentialStore
from app.models.models import SocialAccount

ORIGIN = 'https://localhost:18421'

@pytest.fixture
def tiktok(monkeypatch):
    for key, value in {'OAUTH_ENABLED':'true', 'CLIENT_KEY':'synthetic-client', 'CLIENT_SECRET':'synthetic-secret',
                       'REDIRECT_URI':ORIGIN+yt.CALLBACK, 'EXPECTED_OPEN_ID':''}.items():
        monkeypatch.setenv('TIKTOK_'+key,value)
    calls=[]
    async def provider(method,url,**kwargs):
        calls.append(url)
        if url.endswith('/token/'):
            return {'access_token':'synthetic-tiktok-token','refresh_token':'synthetic-refresh','expires_in':3600,'scope':yt.SCOPE,'open_id':'test-open-id'}
        return {'data':{'user':{'open_id':'test-open-id','display_name':'ET EXPO INC'}},'error':{'code':'ok'}}
    monkeypatch.setattr(yt,'provider',provider)
    return calls

def start(c):
    response=c.post('/api/tiktok/oauth/start',headers={'Origin':ORIGIN})
    assert response.status_code==200,response.text
    return parse_qs(urlsplit(response.json()['authorization_url']).query)['state'][0]

def test_binding_encryption_identity_and_replay(storage,tiktok,caplog):
    c=client(1);state=start(c)
    response=c.get(yt.CALLBACK,params={'state':state,'code':'synthetic'},follow_redirects=False)
    assert response.status_code==303,response.text
    result=c.get('/api/tiktok/accounts')
    assert result.json()['accounts'][0]['external_id']=='test-open-id'
    assert result.json()['real_enabled'] is False
    assert client(2).get('/api/tiktok/accounts').json()['accounts']==[]
    with storage[0]() as db:
        a=db.query(SocialAccount).filter_by(platform='tiktok').one()
        assert a.access_token is None
        assert CredentialStore().get(db,1,f'account:{a.id}','access_token')=='synthetic-tiktok-token'
    assert b'synthetic-tiktok-token' not in open(storage[1].url.database,'rb').read()
    assert 'synthetic-tiktok-token' not in result.text+caplog.text
    assert c.get(yt.CALLBACK,params={'state':state,'code':'synthetic'}).status_code==403
    assert c.post('/api/tiktok/jobs',json={'execution_mode':'REAL'}).status_code==403
    assert len(tiktok)==2

@pytest.mark.parametrize('kind',['anonymous','origin','foreign','denied','wrong','expired'])
def test_guards(storage,tiktok,kind):
    c=client(1)
    if kind=='anonymous':
        assert client().post('/api/tiktok/oauth/start').status_code==401;return
    if kind=='origin':
        assert c.post('/api/tiktok/oauth/start').status_code==403;return
    state=start(c)
    if kind=='foreign':c=client(2)
    if kind=='wrong':state='invalid'
    if kind=='expired':
        from app.models.models import OAuthAttempt
        from app.core.security import utcnow
        from datetime import timedelta
        with storage[0]() as db:
            db.query(OAuthAttempt).update({'expires_at':utcnow()-timedelta(seconds=1)});db.commit()
    r=c.get(yt.CALLBACK,params={'state':state,'code':'synthetic','error':'denied' if kind=='denied' else ''})
    assert r.status_code==(400 if kind=='denied' else 403)
    assert not tiktok

def test_channel_mismatch_not_saved(storage,tiktok,monkeypatch):
    monkeypatch.setenv('TIKTOK_EXPECTED_OPEN_ID','different')
    c=client(1);state=start(c)
    assert c.get(yt.CALLBACK,params={'state':state,'code':'synthetic'}).status_code==409
    assert c.get('/api/tiktok/accounts').json()['accounts']==[]

def test_missing_config_and_cloud_callback(storage,monkeypatch,tiktok):
    monkeypatch.setenv('TIKTOK_CLIENT_SECRET','')
    assert client(1).post('/api/tiktok/oauth/start').status_code==503
    monkeypatch.setenv('TIKTOK_CLIENT_SECRET','synthetic-secret')
    monkeypatch.setenv('MARKETING_CLOUD_MODE','true')
    monkeypatch.setenv('APP_BASE_URL','https://marketing.example.invalid')
    with pytest.raises(Exception) as result:yt.config()
    assert result.value.status_code==503

def test_page_and_readonly_scope(storage,tiktok,monkeypatch):
    c=client(1)
    assert c.get('/tiktok').status_code==200
    assert '/static/js/tiktok.js' in c.get('/tiktok').text
    r=c.post('/api/tiktok/oauth/start',headers={'Origin':ORIGIN})
    query=parse_qs(urlsplit(r.json()['authorization_url']).query)
    assert query['scope']==[yt.SCOPE]
    assert query['redirect_uri']==[ORIGIN+yt.CALLBACK]
    monkeypatch.setenv('TIKTOK_REAL_PUBLISH_ENABLED','true')
    assert c.post('/api/tiktok/jobs').status_code==403

def test_missing_scope_no_storage(storage,tiktok,monkeypatch):
    async def bad_provider(*args,**kwargs):
        return {'access_token':'synthetic-tiktok-token','expires_in':3600,'scope':''}
    monkeypatch.setattr(yt,'provider',bad_provider)
    c=client(1);state=start(c)
    assert c.get(yt.CALLBACK,params={'state':state,'code':'synthetic'}).status_code==400
    assert c.get('/api/tiktok/accounts').json()['accounts']==[]

@pytest.mark.parametrize('profile',[{'data':None},{'data':{'user':None}},{'data':{'user':{'open_id':'different','display_name':'ET EXPO'}}}])
def test_invalid_profile_not_saved(storage,tiktok,monkeypatch,profile):
    original=yt.provider
    async def modified(method,url,**kwargs):
        if method=='GET':return profile
        return await original(method,url,**kwargs)
    monkeypatch.setattr(yt,'provider',modified)
    c=client(1);state=start(c)
    assert c.get(yt.CALLBACK,params={'state':state,'code':'synthetic'}).status_code==400
    assert c.get('/api/tiktok/accounts').json()['accounts']==[]

def test_authorize_url_and_distinct_states(storage,tiktok):
    c=client(1)
    responses=[c.post('/api/tiktok/oauth/start',headers={'Origin':ORIGIN}).json() for _ in range(2)]
    urls=[urlsplit(r['authorization_url']) for r in responses]
    assert all(u.scheme=='https' and u.netloc=='www.tiktok.com' and u.path=='/v2/auth/authorize/' for u in urls)
    queries=[parse_qs(u.query) for u in urls]
    assert queries[0]['state']!=queries[1]['state']
    assert queries[0]['client_key']==['synthetic-client']
    assert queries[0]['disable_auto_auth']==['1']
    assert queries[0]['scope']==['user.info.basic']
    assert c.get('/api/tiktok/oauth/callback',params={'code':'synthetic','state':queries[0]['state'][0]}).status_code==403
