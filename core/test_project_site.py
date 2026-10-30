"""Die Seitentests der Projektseite (site/tests/check_site.py) auch in der
Django-Testsuite: pages.yml prüft erst nach dem Merge auf main, CI schon im
Pull Request. Nach #123 war das Pages-Deployment so tagelang unbemerkt rot."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "site" / "tests" / "check_site.py"
_SPEC = importlib.util.spec_from_file_location("wachwerk_check_site", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

ProjectSiteIntegrityTests = _MODULE.TestSiteIntegrity
ProjectSiteEnglishTests = _MODULE.TestEnglishSite
