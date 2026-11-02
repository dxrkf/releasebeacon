import io
import json
import tempfile
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from releasebeacon import config,history,fetch_release,normalize_release,collect,render_html,atomic_write,valid_repo,MAX_RESPONSE


def release(identity=123,tag='v2.0'):
    return dict(id=identity,tag_name=tag,name='Release '+tag,html_url='https://github.com/example/tool/releases/tag/'+tag,published_at='2026-01-01T00:00:00Z',draft=False,prerelease=False)

class Response(io.BytesIO):pass

class ReleaseTests(unittest.TestCase):
    def test_repo_validation(self):
        for r in ['https://evil.test','a/../b','a/b?x=1','a/..']:
            with self.assertRaises(ValueError):valid_repo(r)
    def test_config(self):self.assertEqual(config({'repositories':[{'repo':'example/tool'}]})[0]['current'],None)
    def test_duplicates(self):
        with self.assertRaises(ValueError):config({'repositories':[{'repo':'Example/tool'},{'repo':'example/Tool'}]})
    def test_missing_config(self):
        with self.assertRaises(ValueError):config({'repositories':[]})
    def test_http_success(self):
        r=fetch_release('example/tool',opener=lambda req,timeout:Response(json.dumps(release()).encode()))
        self.assertEqual(r['tag'],'v2.0')
    def test_fixed_host_and_auth(self):
        def opener(req,timeout):
            self.assertEqual(req.full_url,'https://api.github.com/repos/example/tool/releases/latest');self.assertEqual(req.get_header('Authorization'),'Bearer synthetic-test-token');return Response(json.dumps(release()).encode())
        fetch_release('example/tool','synthetic-test-token',opener=opener)
    def test_404(self):
        def opener(req,timeout):raise urllib.error.HTTPError(req.full_url,404,'Not Found',{},None)
        with self.assertRaisesRegex(ValueError,'404'):fetch_release('example/tool',opener=opener)
    def test_rate_limit(self):
        def opener(req,timeout):raise urllib.error.HTTPError(req.full_url,429,'Limit',{},None)
        with self.assertRaisesRegex(ValueError,'rate limit'):fetch_release('example/tool',opener=opener)
    def test_network_failure(self):
        def opener(req,timeout):raise urllib.error.URLError('offline')
        with self.assertRaisesRegex(ValueError,'network'):fetch_release('example/tool',opener=opener)
    def test_size_limit(self):
        with self.assertRaises(ValueError):fetch_release('example/tool',opener=lambda req,timeout:Response(b'x'*(MAX_RESPONSE+1)))
    def test_unsafe_link(self):
        r=release();r['html_url']='javascript:alert(1)'
        with self.assertRaises(ValueError):normalize_release('example/tool',r)
    def test_prerelease(self):
        r=release();r['prerelease']=True
        with self.assertRaises(ValueError):normalize_release('example/tool',r)
    def test_match_and_first_check(self):
        rows=config({'repositories':[{'repo':'example/tool','current':'v2.0'}]});r,s=collect(rows,{},lambda _:normalize_release('example/tool',release()),'now')
        self.assertEqual(r['results'][0]['status'],'TAG_MATCH');self.assertIsNone(r['results'][0]['changed_since_previous']);self.assertEqual(s['seen']['example/tool'],123)
    def test_difference_and_change(self):
        rows=config({'repositories':[{'repo':'example/tool','current':'v1.0'}]});r,s=collect(rows,{'example/tool':122},lambda _:normalize_release('example/tool',release()),'now')
        self.assertEqual(r['results'][0]['status'],'REVIEW_DIFFERENT_TAG');self.assertTrue(r['results'][0]['changed_since_previous'])
    def test_failure_preserves_history(self):
        def failed(_):raise ValueError('failed')
        r,s=collect(config({'repositories':[{'repo':'example/tool'}]}),{'example/tool':122},failed,'now');self.assertEqual(r['errors'],1);self.assertEqual(s['seen']['example/tool'],122);self.assertNotIn('release',r['results'][0])
    def test_html_escape(self):
        r,_=collect(config({'repositories':[{'repo':'example/tool','current':'<script>alert(1)</script>'}]}),{},lambda _:normalize_release('example/tool',release()),'now');self.assertNotIn('<script>',render_html(r))
    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';atomic_write(p,'first');atomic_write(p,'second');self.assertEqual(p.read_text(),'second');self.assertEqual(len(list(Path(d).iterdir())),1)
    def test_cli_invalid_config(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{}')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('releasebeacon.py')),str(p)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2);self.assertNotIn('Traceback',result.stderr)
    def test_bad_history(self):
        with self.assertRaises(ValueError):history({'format':'releasebeacon-state-v1','seen':{'example/tool':True}})

if __name__=='__main__':unittest.main()
