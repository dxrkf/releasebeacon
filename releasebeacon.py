#!/usr/bin/env python3
"""Online GitHub release watchlist with exact-tag review and local history."""
import argparse
import concurrent.futures
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_RESPONSE=2_000_000
REPO=re.compile(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+')


def valid_repo(value):
    if not isinstance(value,str) or not REPO.fullmatch(value) or value.split('/')[1] in ('.','..'):
        raise ValueError('repository must be owner/name without a URL')
    return value


def config(data):
    if not isinstance(data,dict) or set(data)!={'repositories'} or not isinstance(data['repositories'],list) or not 1<=len(data['repositories'])<=20:
        raise ValueError('configuration requires 1 to 20 repository entries')
    seen=set();result=[]
    for row in data['repositories']:
        if not isinstance(row,dict) or not {'repo'}<=set(row)<= {'repo','current'}:raise ValueError('entry requires repo and optional current')
        repo=valid_repo(row['repo'])
        if repo.lower() in seen:raise ValueError('duplicate repository')
        seen.add(repo.lower())
        current=row.get('current')
        if current is not None and (not isinstance(current,str) or not current or len(current)>1024):raise ValueError('current must be a nonempty exact tag string')
        result.append(dict(repo=repo,current=current))
    return result


def history(data):
    if not isinstance(data,dict) or set(data)!={'format','seen'} or data['format']!='releasebeacon-state-v1' or not isinstance(data['seen'],dict):raise ValueError('invalid history state')
    for repo,identity in data['seen'].items():
        valid_repo(repo)
        if type(identity) is not int or identity<1:raise ValueError('invalid release identity')
    return data['seen']


def normalize_release(repo,data):
    if not isinstance(data,dict) or type(data.get('id')) is not int or data['id']<1 or data.get('draft') is not False or data.get('prerelease') is not False:raise ValueError('unexpected release metadata')
    tag=data.get('tag_name');name=data.get('name') or tag;url=data.get('html_url');date=data.get('published_at')
    if not isinstance(tag,str) or not tag or len(tag)>1024 or not isinstance(name,str) or not isinstance(url,str) or not isinstance(date,str):raise ValueError('incomplete release metadata')
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc!='github.com' or not parsed.path.lower().startswith('/'+repo.lower()+'/releases/'):
        raise ValueError('unexpected release link')
    dt=datetime.fromisoformat(date.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('publication date needs timezone')
    return dict(id=data['id'],tag=tag,name=name[:500],url=url,published_at=date)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def fetch_release(repo,token=None,timeout=15,opener=None):
    valid_repo(repo)
    headers={'User-Agent':'ReleaseBeacon/1.0','Accept':'application/vnd.github+json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request('https://api.github.com/repos/'+repo+'/releases/latest',headers=headers)
    open_request=opener or urllib.request.build_opener(NoRedirect()).open
    try:
        with open_request(request,timeout=timeout) as response:
            raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError('response exceeds 2 MB limit')
            data=json.loads(raw)
        return normalize_release(repo,data)
    except urllib.error.HTTPError as exc:
        if exc.code==404:raise ValueError('HTTP 404: no visible latest release or repository unavailable') from None
        if exc.code in (403,429):raise ValueError(f'HTTP {exc.code}: rate limit or access restriction; retry later') from None
        raise ValueError(f'HTTP {exc.code}: request failed (redirects are not followed)') from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError('network/TLS request failed or timed out') from None


def collect(entries,seen,fetcher,checked_at):
    def one(row):
        repo=row['repo'];result=dict(repo=repo,current=row['current'])
        try:
            release=fetcher(repo)
            result.update(release=release,status='TRACKING' if row['current'] is None else ('TAG_MATCH' if row['current']==release['tag'] else 'REVIEW_DIFFERENT_TAG'),changed_since_previous=None if repo.lower() not in seen else seen[repo.lower()]!=release['id'])
        except (ValueError,UnicodeError,RecursionError) as exc:
            # Render only controlled transport errors; malformed upstream payloads stay generic.
            message=str(exc)
            safe=message if message.startswith(('HTTP ','network/','response exceeds')) else 'Invalid release response from GitHub'
            result.update(status='ERROR',error=safe[:240])
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,entries))
    updated=dict(seen)
    for row in results:
        if row['status']!='ERROR':updated[row['repo'].lower()]=row['release']['id']
    return dict(format='releasebeacon-report-v1',checked_at=checked_at,results=results,errors=sum(r['status']=='ERROR' for r in results)),dict(format='releasebeacon-state-v1',seen=updated)


def render_html(report):
    cards=[]
    for row in report['results']:
        esc=lambda x:html.escape(str(x),quote=True)
        content='<h2>'+esc(row['repo'])+'</h2><p class="badge">'+esc(row['status'])+'</p>'
        if row['status']=='ERROR':content+='<p>'+esc(row['error'])+'</p>'
        else:
            r=row['release'];content+='<p>Configured tag: '+esc(row['current'] or '(tracking only)')+'</p><p>Latest tag: <strong>'+esc(r['tag'])+'</strong></p><p>Published: '+esc(r['published_at'])+'</p><p>Changed since previous check: '+esc(row['changed_since_previous'])+'</p><a href="'+esc(r['url'])+'" rel="noreferrer noopener">Read release notes on GitHub</a>'
        cards.append('<article>'+content+'</article>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>ReleaseBeacon</title><style>body{font:17px system-ui;background:#0d1525;color:#e2e8f0;max-width:1150px;margin:45px auto;padding:24px}h1,a{color:#5eead4}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px}article{background:#1b2a41;padding:24px;border-radius:18px;overflow-wrap:anywhere}.badge{color:#fbbf24}p{line-height:1.6}</style><h1>ReleaseBeacon / online release watchlist</h1><p>Checked: '''+html.escape(report['checked_at'])+'</p><p>Exact tag differences require review. This is not a version-order or upgrade-safety recommendation.</p><div class="grid">'+''.join(cards)+'</div></html>'


def atomic_write(path,text):
    path=Path(path)
    if path.is_symlink():raise ValueError('output symlinks are not supported')
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(text)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('config');p.add_argument('--state',default='.releasebeacon-state.json');p.add_argument('--html');p.add_argument('--json',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--timeout',type=int,default=15)
    args=p.parse_args()
    try:
        if not 1<=args.timeout<=60:raise ValueError('timeout must be 1 to 60 seconds')
        paths=[Path(args.config).resolve(),Path(args.state).resolve()]+([Path(args.html).resolve()] if args.html else [])
        if len(paths)!=len(set(paths)):raise ValueError('config, state and HTML paths must differ')
        entries=config(json.loads(Path(args.config).read_text(encoding='utf-8-sig')))
        state=Path(args.state);seen=history(json.loads(state.read_text(encoding='utf-8'))) if state.exists() else {}
        token=os.environ.get('GITHUB_TOKEN')
        report,newstate=collect(entries,seen,lambda repo:fetch_release(repo,token,args.timeout),datetime.now(timezone.utc).isoformat())
        if args.html:atomic_write(args.html,render_html(report))
        atomic_write(state,json.dumps(newstate,indent=2)+'\n')
        if args.json:print(json.dumps(report,indent=2,ensure_ascii=True))
        else:
            print(f"ReleaseBeacon: {len(report['results'])} repositories, {report['errors']} errors")
            for r in report['results']:
                if r['status']=='ERROR':print(r['repo']+' | ERROR | '+json.dumps(r['error'],ensure_ascii=True))
                else:print(r['repo']+' | '+r['status']+' | '+json.dumps(r['release']['tag'],ensure_ascii=True)+' | changed='+str(r['changed_since_previous']))
            print('Online GitHub API check. No packages downloaded or installed.')
        if report['errors']:return 2
        return int(args.check and any(r['status']=='REVIEW_DIFFERENT_TAG' or r['changed_since_previous'] is True for r in report['results']))
    except (OSError,ValueError,TypeError,RecursionError) as exc:
        print('error: invalid configuration/state, network data or unwritable output',file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
