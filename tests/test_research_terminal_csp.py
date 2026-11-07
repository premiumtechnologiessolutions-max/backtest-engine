"""Synthetic-only CSP regressions: no original gold quotes or trading."""
import base64
import hashlib
import re
import pytest
from scripts.research_terminal_csp import lock_offline_script


HTML = '<!doctype html><html><head><meta charset="utf-8"></head><body><script>const x=1;\n</script></body></html>'


def test_pins_exact_script_bytes_and_keeps_offline_navigation_possible():
    secured = lock_offline_script(HTML)
    body = re.search(r'<script>(.*?)</script>', secured, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode('ascii')
    assert "script-src 'sha256-" + digest + "'" in secured
    assert "script-src 'unsafe-inline'" not in secured
    for restriction in ("default-src 'none'", "connect-src 'none'",
                        "form-action 'none'", "script-src-attr 'none'",
                        "object-src 'none'", "base-uri 'none'"):
        assert restriction in secured
    assert '<script>const x=1;\n</script>' in secured


def test_csp_hash_changes_if_script_changes():
    a = lock_offline_script(HTML)
    b = lock_offline_script(HTML.replace('x=1', 'x=2'))
    assert a != b
    assert re.search(r"script-src 'sha256-([^']+)'", a).group(1) != re.search(
        r"script-src 'sha256-([^']+)'", b).group(1)


@pytest.mark.parametrize('bad', [
    HTML.replace('<script>', '<script src="https://evil.example/x.js">'),
    HTML.replace('</body>', '<script>steal()</script></body>'),
    HTML.replace('</script>', '</SCRIPT>'),
    HTML.replace('const x=1;', '  '),
    HTML.replace('<head>', '<head><head>'),
    HTML.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="default-src *">'),
])
def test_malformed_or_unexpected_scripts_fail_closed(bad):
    with pytest.raises(ValueError):
        lock_offline_script(bad)


def test_rejects_non_string_html():
    with pytest.raises(ValueError):
        lock_offline_script(None)


def test_real_terminal_hash_pins_its_bundled_interactive_controller():
    from scripts.research_terminal_ui import render_premium_html
    model = {
        "updated_utc": "2026-10-29T16:16:00Z",
        "research_status": "HISTORICALLY_EXPOSED_DESIGN_ONLY_NOT_OOS",
        "specifications": 0, "annual_replays": 0, "families": 0,
        "passing_24_of_24": 0, "fee": 0.40, "rows": [],
    }
    html = render_premium_html(model)
    assert html.count('http-equiv="Content-Security-Policy"') == 1
    assert "connect-src 'none'" in html
    assert "script-src 'unsafe-inline'" not in html
    assert 'id="languageToggle"' in html
    script = re.search(r'<script>(.*?)</script>', html, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode('ascii')
    assert "script-src 'sha256-" + digest + "'" in html
