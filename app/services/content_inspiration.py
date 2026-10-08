"""Public URL collection. No cookies, provider secrets, login, proxy or publish adapter."""
import http.client,ipaddress,json,os,re,socket,ssl,subprocess
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,urljoin,parse_qsl,urlencode,quote
from urllib.robotparser import RobotFileParser

ROOT=Path(__file__).resolve().parents[2]
AGENT='ETExpoContentResearch/1.0'
PLATFORMS={'xiaohongshu':['xiaohongshu.com','xhslink.com'],'douyin':['douyin.com'],'tiktok':['tiktok.com'],
 'instagram':['instagram.com'],'facebook':['facebook.com','fb.com'],'linkedin':['linkedin.com'],
 'youtube':['youtube.com','youtu.be'],'bilibili':['bilibili.com','b23.tv'],'weibo':['weibo.com','weibo.cn'],
 'kuaishou':['kuaishou.com'],'zhihu':['zhihu.com'],'wechat':['mp.weixin.qq.com'],'x':['x.com','twitter.com'],'website':[]}
KEYWORDS=['展会搭建','展台设计','参展营销','展览','展台','展会','展位','trade show','tradeshow','booth design','exhibit design','exhibition','exhibitor']

class CollectionError(ValueError):
    pass

def normalize_url(value):
    try:
        u=urlsplit(value.strip())
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError()
        host=u.hostname.encode('idna').decode().lower()
        if any(ord(c)<33 for c in value) or '\\' in value:raise ValueError()
        query=parse_qsl(u.query,keep_blank_values=True)
        # Never accept URLs carrying auth credentials; unknown parameters are retained.
        if any(k.lower() in {'access_token','token','code','password','secret','client_secret','authorization'} for k,v in query):raise ValueError()
        query=[(k,v) for k,v in query if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
        return urlunsplit(('https',host,quote(u.path or '/',safe="/%:@!$&'()*+,;=-._~"),urlencode(query),'') )
    except (ValueError,UnicodeError):raise CollectionError('请提供不含凭据的公开 HTTPS 内容链接（端口 443）。') from None

def platform_for(url):
    host=urlsplit(url).hostname or ''
    return next((p for p,domains in PLATFORMS.items() if any(host==d or host.endswith('.'+d) for d in domains)),'website')

def public_address(host):
    try:addresses=list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    except OSError:raise CollectionError('无法解析来源域名。') from None
    if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise CollectionError('不允许采集本机、内网或保留地址。')
    return addresses[0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,address):
        super().__init__(host,timeout=8,context=ssl.create_default_context());self.address=address
    def connect(self):
        sock=socket.create_connection((self.address,443),self.timeout)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)

def request_once(url,limit=2_000_000):
    u=urlsplit(normalize_url(url));address=public_address(u.hostname)
    conn=PinnedHTTPS(u.hostname,address)
    try:
        conn.request('GET',urlunsplit(('','',u.path,u.query,'')),headers={'User-Agent':AGENT,'Accept':'text/html,text/plain;q=0.9','Accept-Encoding':'identity'})
        response=conn.getresponse();headers={k.lower():v for k,v in response.getheaders()}
        if headers.get('content-encoding','identity').lower() not in {'identity',''}:
            raise CollectionError('来源返回不受支持的压缩格式，未继续解析。')
        raw=response.read(limit+1)
        if len(raw)>limit:raise CollectionError('来源响应超过大小限制。')
        return response.status,headers,raw
    except (OSError,http.client.HTTPException):raise CollectionError('来源请求失败或超时；未使用登录凭据或绕过限制。') from None
    finally:conn.close()

def robots_allowed(url):
    u=urlsplit(url);robot=urlunsplit((u.scheme,u.netloc,'/robots.txt','',''))
    status,headers,raw=request_once(robot,256_000)
    if status==404:return
    if status!=200:raise CollectionError('无法确认来源 robots.txt 许可；本次未采集正文。')
    parser=RobotFileParser();parser.parse(raw.decode('utf-8',errors='replace').splitlines())
    if not parser.can_fetch(AGENT,url):raise CollectionError('来源 robots.txt 不允许采集此内容。')

def collect(url):
    original=normalize_url(url);current=original
    for _ in range(4):
        robots_allowed(current)
        status,headers,raw=request_once(current)
        if status in {301,302,303,307,308}:
            current=normalize_url(urljoin(current,headers.get('location','')));continue
        if status!=200:raise CollectionError('来源返回 HTTP '+str(status)+'；请使用有权限的文案导入或平台数据接口。')
        if 'text/html' not in headers.get('content-type',''):raise CollectionError('当前入口只提取 HTML 文案，不下载视频或文件。')
        html=raw.decode('utf-8',errors='replace')
        if re.search(r'<title[^>]*>[^<]*(sign in|log in|登录|验证码|security check|captcha)',html,re.I):
            raise CollectionError('来源要求登录或验证；未自动登录或绕过。')
        python=ROOT/'.venv-content/Scripts/python.exe'
        if not python.exists():raise CollectionError('文案提取组件尚未安装，请按 CONTENT_INSPIRATION.md 恢复。')
        try:
            result=subprocess.run([str(python),'-X','utf8','-B',str(ROOT/'scripts/extract_inspiration.py')],
                input=json.dumps({'html':html,'url':current}),capture_output=True,text=True,encoding='utf-8',timeout=20,
                env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP'}})
            if result.returncode:raise ValueError()
            doc=json.loads(result.stdout)
        except (subprocess.TimeoutExpired,ValueError):raise CollectionError('正文提取失败；未保存为成功。') from None
        if len(doc.get('excerpt',''))<40:raise CollectionError('未获得可用正文，可能是动态页面或登录限制；请导入有权限的文案。')
        doc.update(source_url=original,resolved_url=current,platform=platform_for(current),capture_method='PUBLIC_URL',metrics={},metrics_source='UNAVAILABLE')
        return doc
    raise CollectionError('来源重定向次数过多。')

def annotate(doc):
    text=(doc.get('title','')+' '+doc.get('excerpt','')).lower()
    matches=[k for k in KEYWORDS if k in text]
    doc['topic_matches']=matches
    doc['topic_status']='MATCHED' if matches else 'NEEDS_REVIEW'
    doc['heat_status']=doc.get('heat_evidence',{}).get('status','UNVERIFIED')
    doc['analysis']={'method':'RULE_BASED_NOT_AI','opening':('QUESTION' if '?' in text or '？' in text else 'STATEMENT'),
                     'has_numbers':bool(re.search(r'\d',text)),
                     'suggested_outline':['参展客户的具体问题','展台设计或搭建方案','可核实的案例与结果','邀请咨询或讨论'],
                     'note':'结构提示，不代表已验证爆款或预测传播效果。'}
    return doc
