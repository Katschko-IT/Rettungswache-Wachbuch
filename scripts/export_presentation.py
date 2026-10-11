"""Render the real Django template; export a DB-free isolated presentation preview."""
import os
import re
import shutil
import sys
from pathlib import Path

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--source-url', required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
out = args.output
sys.path.insert(0, str(repo))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.test_settings')
os.environ.setdefault('SECRET_KEY', 'isolated-presentation-export-not-a-server-secret')
os.environ.setdefault('DB_NAME', '/opt/data/cache/presentation-qa/unused-export.sqlite3')
import django
django.setup()
from django.contrib.auth.models import AnonymousUser
from django.template.loader import get_template

out.mkdir(parents=True, exist_ok=True)
html = get_template('core/landing.html').render({
    'app_name': 'Wachwerk', 'user': AnonymousUser(), 'demo_mode': False,
    'source_url': args.source_url,
})
# Auth/backend and legal paths lead to the existing real demo, not this static preview.
html = re.sub(r'(href=[\"\'])(/(?!static/)[^\"\']+)([\"\'])',
              lambda m: m[1] + 'https://wachbuch-demo.46-225-106-237.sslip.io' + m[2] + m[3], html)
(out / 'index.html').write_text(html)
asset_out = out / 'static/core'
asset_out.mkdir(parents=True, exist_ok=True)
for name in ('presentation.css', 'presentation.js'):
    shutil.copy2(repo / 'core/static/core' / name, asset_out / name)
shutil.copytree(repo / 'core/static/core/fonts', asset_out / 'fonts', dirs_exist_ok=True)
shutil.copytree(repo / 'core/static/core/icons', asset_out / 'icons', dirs_exist_ok=True)
shutil.copytree(repo / 'core/static/core/vendor', asset_out / 'vendor', dirs_exist_ok=True)
assert 'data-pw-demo' in html, 'Presentation markup missing'
assert 'presentation.css' in html and 'presentation.js' in html
print(f'EXPORTED {out}: real Django template, two local assets, no database writes')
