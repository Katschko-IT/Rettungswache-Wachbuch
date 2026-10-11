"""Browser regression for PWA install UI using real app.js/app.css.
Native install events/display modes are simulated; this is NOT an OS install test.
Run with PYTHONPATH pointing to the installed Playwright package.
"""
import argparse
import functools
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--report',type=Path,default=Path('/opt/data/cache/app-ui-qa/install-browser-report.json'))
args=parser.parse_args()
HTML='''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/core/static/core/app.css"></head><body><div class="install-banner" data-install-banner hidden><div><strong>Wachwerk auf dem Gerät</strong><span>Als App installieren für schnellen Zugriff auf der Wache.</span></div><div class="install-actions"><button type="button" class="button primary" data-install-button>Installieren</button><button type="button" class="button secondary" data-install-dismiss>Später</button><button type="button" class="button secondary install-close" data-install-dismiss aria-label="Installationshinweis schließen">×</button></div></div><script defer src="/core/static/core/app.js"></script></body></html>'''
# Test the actual new shell's banner markup, not just a hand-written fixture.
base=(args.root/'templates/base.html').read_text()
match=re.search(r"{% if current_membership and current_membership.role != 'auditor' %}(.*?){% endif %}",base,re.S)
APP_HTML=HTML[:HTML.index('<body>')]+('<body class="ww-app"><link rel="stylesheet" href="/core/static/core/app-ui.css">'+match.group(1).replace('{{ app_name }}','Wachwerk')+'<script defer src="/core/static/core/app.js"></script></body></html>') if match else HTML
class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):pass
    def do_GET(self):
        if self.path.startswith('/fixture'):
            body=(APP_HTML if self.path.startswith('/fixture-app') else HTML).encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        elif self.path.startswith('/service-worker.js'):
            self.send_response(200);self.send_header('Content-Type','text/javascript');self.end_headers();self.wfile.write(b'')
        else:super().do_GET()
handler=functools.partial(Handler,directory=str(args.root))
server=ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/fixture'
checks=[]
errors=[]
OFFER='''(outcome) => {
 const event=new Event('beforeinstallprompt',{cancelable:true});
 window.promptCalls=0;
 event.prompt=async () => {window.promptCalls++; if(outcome==='error') throw new Error('test rejection'); return {outcome};};
 event.userChoice=outcome==='error'?undefined:Promise.resolve({outcome});
 window.dispatchEvent(event);
 return event.defaultPrevented;
}'''
def offer(page,outcome='dismissed'):
    assert page.evaluate(OFFER,outcome),'Native prompt must be prevented'
def hidden(page):
    assert page.locator('[data-install-banner]').is_hidden(),'Install banner unexpectedly visible'
    assert page.locator('[data-install-banner]').evaluate("el => getComputedStyle(el).display")=='none','hidden overridden by CSS'
def visible(page):
    assert page.locator('[data-install-banner]').is_visible(),'Expected install offer missing'
def record(name):checks.append(name)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
    def context(init=None,storage=None):
        c=browser.new_context(viewport={'width':390,'height':844},service_workers='block')
        if init:c.add_init_script(init)
        p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
        p.goto(url);p.wait_for_load_state('networkidle')
        if storage:p.evaluate(storage)
        return c,p
    try:
        c,p=context();hidden(p);record('default hidden: genuine CSS + JS, no install event')
        offer(p);visible(p);record('native install offer makes banner actionable')
        p.get_by_role('button',name='Später',exact=True).click();hidden(p)
        offer(p);hidden(p);record('later persists and repeated install event does not reshow')
        p.reload();offer(p);hidden(p);record('later survives page reload')
        p.goto(url+'?next=1');offer(p);hidden(p);record('later survives navigation')
        c.close()
        c,p=context();offer(p);visible(p)
        p.get_by_role('button',name='Installationshinweis schließen').click();hidden(p);offer(p);hidden(p)
        record('separate close button dismisses, repeat event stays hidden');c.close()
        c,p=context();offer(p);visible(p);p.reload();offer(p);hidden(p)
        record('automatic suggestion occurs at most once per tab session');c.close()
        c,p=context(storage="localStorage.setItem('rwsth-install-dismissed',String(Date.now()-8*24*60*60*1000))")
        offer(p);hidden(p);record('past dismissal remains permanent, including legacy timestamps');c.close()
        for mode in ('standalone','minimal-ui','fullscreen'):
            init="""(() => {const original=window.matchMedia.bind(window);window.matchMedia=(q) => q==='(display-mode: MODE)'?{matches:true,media:q,addEventListener(){},removeEventListener(){}}:original(q);})();""".replace('MODE',mode)
            c,p=context(init);hidden(p);offer(p);hidden(p)
            assert p.evaluate("localStorage.getItem('rwsth-installed')")=='1'
            record(f'installed display-mode {mode} suppresses hint');c.close()
        c,p=context("Object.defineProperty(navigator,'standalone',{get:()=>true})")
        hidden(p);offer(p);hidden(p);record('iOS navigator.standalone suppresses hint');c.close()
        c,p=context();offer(p);visible(p);p.evaluate("window.dispatchEvent(new Event('appinstalled'))")
        hidden(p);assert p.evaluate("localStorage.getItem('rwsth-installed')")=='1'
        p.reload();hidden(p);record('appinstalled hides UI and remembers installation across reload');c.close()
        c,p=context(storage="localStorage.setItem('rwsth-installed','1')")
        p.reload();hidden(p);offer(p);visible(p)
        assert p.evaluate("localStorage.getItem('rwsth-installed')") is None
        record('fresh authoritative install offer supersedes stale installed marker');c.close()
        for outcome in ('accepted','dismissed','error'):
            c,p=context();offer(p,outcome);visible(p)
            p.get_by_role('button',name='Installieren',exact=True).click();hidden(p)
            p.wait_for_function("!document.querySelector('[data-install-button]').disabled")
            assert p.evaluate('window.promptCalls')==1
            if outcome=='accepted':
                assert p.evaluate("localStorage.getItem('rwsth-installed')") is None,'Acceptance is not installation proof'
            else:
                offer(p);hidden(p)
            record(f'native prompt {outcome}: one invocation, no stuck button or unhandled rejection');c.close()
        c,p=context("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}});Object.defineProperty(window,'sessionStorage',{get(){throw new Error('blocked')}})")
        hidden(p);offer(p);visible(p);p.get_by_role('button',name='Später',exact=True).click();hidden(p);offer(p);hidden(p)
        record('blocked storage: graceful operation and page-level dismissal');c.close()
        c,p=context();offer(p);visible(p)
        other=c.new_page();other.goto(url);other.wait_for_load_state('networkidle')
        other.evaluate("localStorage.setItem('rwsth-install-dismissed',String(Date.now()))")
        p.wait_for_function("document.querySelector('[data-install-banner]').hidden")
        hidden(p);record('dismissal in another tab hides existing suggestion');c.close()
        init="""(() => { const original=window.matchMedia.bind(window);window.modeQuery={matches:false,media:'(display-mode: standalone)',addEventListener(type,fn){this.listener=fn;}};window.matchMedia=q=>q===window.modeQuery.media?window.modeQuery:original(q);})();"""
        c,p=context(init);offer(p);visible(p)
        p.evaluate("window.modeQuery.matches=true;window.modeQuery.listener()")
        hidden(p);record('runtime display-mode change hides suggestion immediately');c.close()
        c,p=context();p.set_viewport_size({'width':320,'height':740});offer(p);visible(p)
        p.evaluate("document.documentElement.style.fontSize='200%'")
        assert p.evaluate('document.documentElement.scrollWidth <= innerWidth'), '320px/200% overflow'
        record('320px and 200% font: no page overflow');c.close()
        c,p=context();p.goto(url.replace('/fixture','/fixture-app'));p.wait_for_load_state('networkidle')
        hidden(p);offer(p);hidden(p);p.reload();offer(p);hidden(p)
        assert p.get_by_role('button',name='Später',exact=True).count()==0
        record('actual app shell: no automatic prompt after install event, reload or navigation; no Later button')
        for width in (320,390,1280):
            p.set_viewport_size({'width':width,'height':844})
            # Inspect placement on an explicitly visible existing window only.
            p.evaluate("document.querySelector('[data-install-banner]').hidden=false")
            bounds=p.evaluate("""() => {const b=document.querySelector('[data-install-banner]').getBoundingClientRect();const x=document.querySelector('.install-close').getBoundingClientRect();return {right:b.right-x.right,top:x.top-b.top,w:x.width,h:x.height};}""")
            assert 0 <= bounds['right'] <= 16 and 0 <= bounds['top'] <=16,bounds
            assert bounds['w']>=48 and bounds['h']>=48,bounds
            record(f'actual shell X upper-right at {width}px, 48px touch target')
        p.get_by_role('button',name='Installationshinweis schließen').click();hidden(p)
        assert p.evaluate("localStorage.getItem('rwsth-install-dismissed')")=='permanent'
        offer(p);hidden(p);p.reload();offer(p);hidden(p)
        record('actual shell X closes permanently; native events never reshow it');c.close()
        assert not errors,errors
        record('no uncaught JavaScript errors in any tested scenario')
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps({'status':'passed','engine':'chromium','real_assets':True,'native_events_simulated':True,'checks':checks,'count':len(checks),'errors':errors},ensure_ascii=False,indent=2))
        print(f'PWA INSTALL BROWSER QA PASSED: {len(checks)} checks; real JS/CSS, simulated native events; zero uncaught JS errors')
    finally:
        browser.close();server.shutdown()
