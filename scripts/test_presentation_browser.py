import functools
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(os.environ.get('PRESENTATION_QA_DIR', '/opt/data/cache/presentation-qa'))
url = sys.argv[1] if len(sys.argv) > 1 else None
server = None
if not url:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(out / 'dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
exe = os.environ.get('CHROMIUM_EXECUTABLE', '/opt/hermes/.playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell')
evidence = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, headless=True, args=['--no-sandbox'])
        for label, width, height in [('desktop',1440,1000), ('mobile',390,844), ('narrow',320,740), ('tablet',768,1024), ('transition',960,900), ('laptop',992,900), ('landscape',844,390)]:
            page = browser.new_page(viewport={'width':width,'height':height}, reduced_motion='reduce')
            errors, requests = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type=='error' else None)
            page.on('request', lambda r: requests.append({'url':r.url, 'method':r.method, 'type':r.resource_type}))
            page.on('response', lambda r: errors.append(f'HTTP {r.status}: {r.url}') if r.status >= 400 else None)
            assert page.goto(url, wait_until='networkidle').status == 200
            assert page.locator('h1').count() == 1
            assert page.locator('.pw-platforms a').get_attribute('href') == 'https://github.com/darkspike1988/Rettungswache-Wachbuch'
            assert page.locator('.pw-platform img').count() == 3
            for image in page.locator('.pw-platform img').all():
                assert image.evaluate('(e)=>e.complete && e.naturalWidth > 0'), 'Missing platform icon'
            assert page.locator('.pw-platform-note').is_visible()
            assert page.locator('h1').inner_text() == 'Die nächste Schicht. Schon im Bild.'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
            for button in page.locator('[data-pw-demo] button').all():
                if button.is_visible():
                    assert button.bounding_box()['height'] >= 47.5, 'Touch target below 48px'
            phone = page.locator('.pw-device').bounding_box()
            reset = page.locator('[data-pw-reset]').bounding_box()
            platforms = page.locator('.pw-platforms').bounding_box()
            assert reset['y'] >= phone['y'] + phone['height'], 'Reset must follow device'
            assert platforms['y'] > reset['y'], 'Platform labels must not delay demo entry'
            if width <= 390:
                assert phone['y'] < height - 80, 'Device must be discoverable in first viewport'
            for platform in page.locator('span.pw-platform').all():
                assert platform.evaluate('(e)=>getComputedStyle(e).borderTopStyle') == 'none'
                assert platform.get_attribute('tabindex') is None
            assert page.locator('.pw-brand').bounding_box()['height'] >= 48
            # Real keyboard entry and visible focus, including the skip link.
            page.keyboard.press('Tab')
            assert page.locator(':focus').get_attribute('href') == '#inhalt'
            assert page.locator(':focus').evaluate('(e)=>getComputedStyle(e).outlineStyle') != 'none'
            if width < 960:
                assert not page.locator('.pw-header .pw-nav').is_visible()
                menu = page.locator('.pw-mobile-menu')
                menu.locator('summary').click()
                assert menu.get_attribute('open') is not None
                page.keyboard.press('Escape')
                assert menu.get_attribute('open') is None
                menu.locator('summary').click()
                menu.locator('a[href="#demo"]').click()
                assert menu.get_attribute('open') is None
                primary, secondary = page.locator('.pw-hero .pw-cta a').all()
                first, second = primary.bounding_box(), secondary.bounding_box()
                assert second['y'] >= first['y'] + first['height'], 'Incorrect CTA order'
                assert abs(first['width'] - second['width']) < 1, 'Unequal mobile CTA widths'
                assert first['width'] >= width - 42, 'Mobile CTA not full-width'
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(out / f'header-{label}.png'))
            assert page.locator('.pw-demo .pw-lead').inner_text() == 'Vorschau mit fiktiven Beispieldaten – keine echte App-Sitzung.'
            page.locator('[data-pw-start]').first.click()
            # Regression: opening a revision must never destroy overview card text.
            expected_titles = page.locator('[data-pw-ho] strong').all_text_contents()
            for index, revision in [(0,'3'), (1,'2'), (2,'1')]:
                page.locator('[data-pw-view="overview"]').click()
                page.locator('[data-pw-ho]').nth(index).click()
                assert page.locator('[data-pw-ho-title]').inner_text() == expected_titles[index]
                assert page.locator('[data-pw-panel="handover"] [data-pw-rev]').first.inner_text() == revision
                assert page.locator('[data-pw-rev-item]:visible').count() == int(revision)
                page.locator('[data-pw-ack]').click()
                assert f'Revision {revision} bestätigt' in page.locator('[data-pw-ack-status]').inner_text()
                assert 'bleibt offen' in page.locator('[data-pw-ack-status]').inner_text()
                assert page.locator('[data-pw-ho] strong').all_text_contents() == expected_titles
            page.locator('[data-pw-view="tasks"]').click()
            tasks = page.locator('[data-pw-task]')
            tasks.first.check()
            assert page.locator('[data-pw-task-count]').inner_text() == '1 von 7 erledigt'
            page.locator('[data-pw-view="calendar"]').click()
            assert page.locator('[data-pw-panel="calendar"]').is_visible()
            page.locator('[data-pw-reset]').click()
            assert tasks.evaluate_all('(es)=>es.every(e=>!e.checked)')
            assert page.locator('[data-pw-task-count]').inner_text() == '0 von 7 erledigt'
            assert page.locator('[data-pw-panel="overview"]').is_visible()
            page.locator('[data-pw-view="handover"]').focus()
            page.keyboard.press('Enter')
            assert page.locator('[data-pw-panel="handover"]').is_visible()
            assert page.locator('[data-pw-panel="handover"] [data-pw-rev]').first.inner_text() == '3'
            page.locator('[data-pw-reset]').click()
            # Regression: transition after inner scrolling, not only fresh panel clicks.
            for state in ['handover', 'tasks', 'calendar', 'overview']:
                page.locator('.pw-screen').evaluate('(e)=>e.scrollTop=e.scrollHeight')
                page.locator('[data-pw-view="' + state + '"]').click()
                assert page.locator('.pw-screen').evaluate('(e)=>e.scrollTop') == 0, state
            # Text enlargement: bounds matter even when overflow is concealed.
            style = page.add_style_tag(content='html { font-size: 200% !important; }')
            if page.locator('.pw-mobile-menu').is_visible():
                menu = page.locator('.pw-mobile-menu')
                box = menu.locator('summary').bounding_box()
                assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, '200% menu clipped'
                menu.locator('summary').click()
                for link in menu.locator('a').all():
                    box = link.bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, '200% menu link clipped'
                page.keyboard.press('Escape')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), '200% page overflow'
            for state in ['overview', 'handover', 'tasks', 'calendar']:
                page.locator('[data-pw-view="' + state + '"]').click()
                for control in page.locator('.pw-screen button:visible, .pw-screen label:visible').all():
                    box = control.bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, '200% screen control clipped'
            style.evaluate('(e)=>e.remove()')
            page.locator('.pw-faq summary').first.click()
            assert page.locator('.pw-faq details').first.get_attribute('open') == ''
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not page.evaluate('Object.keys(localStorage).length + Object.keys(sessionStorage).length')
            assert not any(r['type'] in ['fetch','xhr'] or r['method'] != 'GET' for r in requests)
            # Opt-in slides use the browser clock; they never change acknowledgements/tasks.
            play = page.locator('[data-pw-play]')
            assert play.get_attribute('aria-pressed') == 'false'
            page.clock.install()
            play.click()
            assert play.get_attribute('aria-pressed') == 'true'
            page.clock.run_for(6500)
            assert page.locator('[data-pw-panel="handover"]').is_visible()
            assert page.locator('[data-pw-ack-status]').inner_text() == 'Noch nicht gelesen.'
            page.locator('[data-pw-view="tasks"]').click()
            assert play.get_attribute('aria-pressed') == 'false'
            page.clock.run_for(7000)
            assert page.locator('[data-pw-panel="tasks"]').is_visible()
            play.click()
            page.keyboard.press('Escape')
            assert play.get_attribute('aria-pressed') == 'false'
            play.click()
            page.clock.run_for(26000)
            assert play.get_attribute('aria-pressed') == 'false'
            assert page.locator('[data-pw-panel="calendar"]').is_visible()
            page.clock.run_for(13000)
            assert page.locator('[data-pw-panel="calendar"]').is_visible()
            assert page.locator('[data-pw-task]:checked').count() == 0
            assert page.locator('.pw-view.is-on').evaluate('(e)=>getComputedStyle(e).animationName') == 'none'
            page.locator('[data-pw-reset]').click()
            assert not errors, errors
            page.screenshot(path=str(out / f'after-{label}.png'), full_page=True)
            page.locator('#demo').screenshot(path=str(out / f'phone-{label}.png'))
            evidence.append({'viewport':{'width':width,'height':height}, 'flows':'all passed', 'console_errors':errors, 'requests':requests})
            page.close()
        page = browser.new_page(java_script_enabled=False, viewport={'width':390,'height':844})
        page.goto(url)
        assert page.locator('noscript').is_visible()
        assert page.get_by_role('link', name='Vorführung ansehen').is_visible()
        evidence.append({'javascript_disabled':'fallback visible'})
        browser.close()
finally:
    if server:
        server.shutdown()
(out / 'browser-evidence.json').write_text(json.dumps({'url':url,'checks':evidence}, indent=2))
print(f'BROWSER QA PASSED: {len(evidence)-1} viewports, three handover revisions, task/ack separation, reset, keyboard, FAQ, reduced motion, no-JS fallback, no XHR or storage')
