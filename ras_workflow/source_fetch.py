"""Bounded, TLS-verified public-source discovery and selective ZIP reads."""
import io
import ipaddress
import json
import socket
import urllib.parse
import urllib.request
import urllib.error
import zipfile
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath

ALLOWED = ('usgs.gov', 'sciencebase.gov', 'amazonaws.com', 'fema.gov',
           'hydro.nationalmap.gov', 'tigerweb.geo.census.gov')

def public_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS sources are supported')
    host = (p.hostname or '').lower()
    if not any(host == a or host.endswith('.'+a) for a in ALLOWED):
        raise ValueError('Source host is not in the supported public-source allowlist')
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private/local source address is not allowed')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class PublicDownloadRequired(ValueError):
    """Public download needs a human browser step, not a File Manager account."""
    def __init__(self, message, page_url, reason):
        super().__init__(message)
        self.page_url,self.reason=page_url,reason

class PublicDownloadForms(HTMLParser):
    def __init__(self):
        super().__init__();self.forms=[];self.current=None;self.button=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form':
            self.current=dict(action=attrs.get('action',''),method=attrs.get('method','get').lower(),label='')
        elif tag=='button' and self.current is not None:self.button=True
    def handle_endtag(self,tag):
        if tag=='button':self.button=False
        if tag=='form':
            if self.current is not None:self.forms.append(self.current)
            self.current=None;self.button=False
    def handle_data(self,data):
        if self.current is not None and self.button:self.current['label']+=data

def public_download_form(html,item_id,name):
    """Read the exact named attachment's observed form, without guessing URLs."""
    if not re.fullmatch(r'[0-9a-f]{24}',item_id):raise ValueError('Invalid ScienceBase item ID')
    page=CATALOG+item_id;parser=PublicDownloadForms();parser.feed(html)
    forms=[f for f in parser.forms if f['label'].strip()==name and f['method']=='post']
    if len(forms)!=1:raise PublicDownloadRequired('Public attachment form not found uniquely; open the catalog Attached Files list.',page,'FORM_CHANGED')
    action=urllib.parse.urljoin(page,forms[0]['action']);parts=urllib.parse.urlsplit(action)
    if parts.scheme!='https' or parts.netloc!='www.sciencebase.gov' or parts.path!='/catalog/item/managerRequestDownload/'+item_id:
        raise ValueError('Unexpected public download form destination')
    values=urllib.parse.parse_qs(parts.query,strict_parsing=True)
    if set(values)!={'filePath'} or len(values['filePath'])!=1:raise ValueError('Unexpected public download form fields')
    file=urllib.parse.urlsplit(values['filePath'][0])
    if file.scheme!='https' or file.username or file.password or file.port not in (None,443) or not (file.hostname or '').endswith('.s3.amazonaws.com') or file.query or file.fragment:
        raise ValueError('Unexpected public file target')
    if urllib.parse.unquote(file.path)!='/'+item_id+'/'+name:raise ValueError('Public form does not identify the selected attachment')
    return action

class NoDownloadRedirect(Redirect):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        return None  # Resolve the public link before reading any archive bytes.

def resolve_public_archive(download,item_id,name):
    """Use the anonymous catalog form. Never call authenticated File Manager APIs.

    CAPTCHA/login responses stop here. No cookie/token export, CAPTCHA solving,
    or full-archive fallback is attempted. A signed redirect is used only in memory.
    """
    if not re.fullmatch(r'[0-9a-f]{24}',item_id):raise ValueError('Invalid ScienceBase item ID')
    page=CATALOG+item_id
    action=public_download_form(download.get(page).decode('utf-8'),item_id,name)
    public_url(action)
    opener=urllib.request.build_opener(NoDownloadRedirect())
    request=urllib.request.Request(action,data=b'',method='POST',headers={'Content-Type':'application/x-www-form-urlencoded','Accept-Encoding':'identity'})
    try:
        with opener.open(request,timeout=download.timeout) as response:
            allowance=min(100_000,download.limit-download.used)
            if allowance<=0:raise ValueError('Source download budget reached')
            raw=response.read(allowance);download.used+=len(raw)
            text=raw.decode('utf-8',errors='replace').casefold()
            if 'captcha check' in text or 'g-recaptcha' in text:
                raise PublicDownloadRequired('The public catalog download requested a CAPTCHA. Open Attached Files in your browser, complete the verification yourself, then import the downloaded single-site folder. A File Manager account is not required.',page,'CAPTCHA')
            raise PublicDownloadRequired('The public catalog returned a webpage rather than a file redirect. Open Attached Files and download the named ZIP in your browser; do not use File Manager.',page,'PUBLIC_PAGE')
    except urllib.error.HTTPError as e:
        try:
            if e.code in (301,302,303,307,308) and e.headers.get('Location'):
                url=urllib.parse.urljoin(action,e.headers['Location']);p=urllib.parse.urlsplit(url)
                if not (p.hostname or '').endswith('.amazonaws.com'):
                    raise PublicDownloadRequired('Public download did not redirect to a data file. Use the catalog Attached Files list; authenticated manager routes are not used.',page,'PUBLIC_REDIRECT')
                public_url(url)
                if urllib.parse.unquote(p.path)!='/'+item_id+'/'+name:raise ValueError('Public download redirect changed the attachment identity')
                return url
            if e.code in (401,403):
                raise PublicDownloadRequired('This automated public download was rejected. Open the catalog Attached Files list in your browser; this does not establish that the dataset needs a File Manager account.',page,'AUTOMATED_REQUEST_REJECTED') from None
            raise
        finally:e.close()

class Download:
    def __init__(self, limit=80_000_000, timeout=12):
        self.limit, self.timeout, self.used = limit, timeout, 0
        self.opener = urllib.request.build_opener(Redirect())

    def get(self, url, limit=2_000_000, byte_range=None):
        public_url(url)
        headers = {'User-Agent':'SteadyReach public-source acquisition', 'Accept-Encoding':'identity'}
        if byte_range is not None: headers['Range'] = 'bytes=%d-%d' % byte_range
        allowance = min(limit, self.limit-self.used)
        if allowance <= 0: raise ValueError('Source download budget reached; saved files retained')
        with self.opener.open(urllib.request.Request(url, headers=headers), timeout=self.timeout) as response:
            if byte_range is not None:
                expected = 'bytes %d-%d/' % byte_range
                if response.status != 206 or not response.headers.get('Content-Range','').startswith(expected):
                    raise ValueError('Server does not honor bounded ZIP range reads; full archive was not downloaded')
            size = response.headers.get('Content-Length')
            if size and int(size) > allowance: raise ValueError('Source exceeds the remaining download allowance')
            raw = response.read(allowance+1)
            self.used += len(raw)
            if len(raw) > allowance: raise ValueError('Source exceeds download allowance')
            if byte_range and len(raw) != byte_range[1]-byte_range[0]+1: raise ValueError('Incomplete range response')
            return raw

    def json(self, url): return json.loads(self.get(url))

class RemoteZip(io.RawIOBase):
    def __init__(self, download, url, size):
        self.download, self.url, self.size, self.pos = download, url, int(size), 0
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        pos = offset if whence == 0 else self.pos+offset if whence == 1 else self.size+offset
        if not 0 <= pos <= self.size: raise ValueError('Invalid archive seek')
        self.pos = pos
        return pos
    def read(self, n=-1):
        n = min(self.size-self.pos, n if n >= 0 else self.size-self.pos)
        if not n: return b''
        if n > 16_000_000: raise ValueError('Archive member/range is too large')
        raw = self.download.get(self.url, n, (self.pos,self.pos+n-1)); self.pos += len(raw)
        return raw

def survey_members(download, entry, site_id):
    """Read only the matching site's source documents, never native models."""
    # A manager URL may return an HTML sign-in page, not the source artifact.
    if download.get(entry['url'],4,(0,3)) != b'PK\x03\x04':
        raise ValueError('Official archive link returned a webpage instead of ZIP. Open the catalog download link or import the downloaded single-site folder; credentials are not requested or bypassed.')
    with zipfile.ZipFile(RemoteZip(download, entry['url'], entry['size'])) as archive:
        chosen=[]
        for z in archive.infolist():
            path=PurePosixPath(z.filename.replace('\\','/'))
            if path.is_absolute() or '..' in path.parts: continue
            if not any(p.startswith(str(site_id)+'_') for p in path.parts): continue
            if z.is_dir() or path.suffix.lower() not in ('.csv','.pdf','.jpg','.jpeg','.png','.txt','.xml'): continue
            if z.file_size > 15_000_000 or z.compress_size > 15_000_000: continue
            chosen.append(z)
        if not chosen: raise ValueError('No matching site documents in survey archive')
        if len(chosen)>100 or sum(z.file_size for z in chosen)>80_000_000: raise ValueError('Site source subset exceeds extraction allowance')
        chosen.sort(key=lambda z: ('/Photos/' in z.filename.replace('\\','/'),z.filename))
        for z in chosen:
            yield z.filename, archive.read(z)

CATALOG = 'https://www.sciencebase.gov/catalog/item/'
MA_RELEASE = '6a5fd9261ba49b6a914ce2d1'
MA_SURVEY = '6a6266c11ba49bb7d9d0603a'

def search_url(lat, lon):
    spatial=json.dumps({'type':'Polygon','coordinates':[[[lon-.01,lat-.01],[lon+.01,lat-.01],[lon+.01,lat+.01],[lon-.01,lat+.01],[lon-.01,lat-.01]]]},separators=(',',':'))
    return 'https://www.sciencebase.gov/catalog/items?'+urllib.parse.urlencode({'format':'json','max':10,'q':'culvert survey','filter':'spatialQuery='+spatial})
