"""Read-only browser dashboard static contract checks; no JS server startup."""
from html.parser import HTMLParser
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "web" / "quant-control" / "index.html"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.section_ids = set()
        self.script_bodies = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        info = dict(attrs)
        if "id" in info:
            assert info["id"] not in self.ids
            self.ids.add(info["id"])
        if tag == "section":
            self.section_ids.add(info.get("id"))
        if tag == "script":
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.script_bodies.append(data)


def test_static_dashboard_has_accessible_local_file_controls():
    html = DASHBOARD.read_text(encoding="utf-8")
    tags = Tags()
    tags.feed(html)
    assert {"file", "clear", "strategy-count", "task-count",
            "shard-count", "health", "engines", "reviewers",
            "missing", "error"} <= tags.ids
    assert tags.section_ids == {"overview", "integrations", "gates"}
    assert 'type="file"' in html
    assert "No status file loaded" in html
    assert "NOT READY FOR MARKET RUNS" in html


def test_browser_page_is_deliberately_offline_and_no_secret_content():
    html = DASHBOARD.read_text(encoding="utf-8")
    scripts = Tags()
    scripts.feed(html)
    code = "\n".join(scripts.script_bodies)
    assert "connect-src 'none'" in html
    assert 'default-src \'none\'' in html
    assert "file.text()" in code
    assert "textContent" in code
    for disallowed in (
        "fetch(", "XMLHttpRequest", "WebSocket", "innerHTML",
        "navigator.sendBeacon", "localStorage", "eval(", "new Function",
        "BROKER_TOKEN", "api_key",
    ):
        assert disallowed not in code
    assert "market_research_authorized !== false" in code


def test_status_not_misrepresented_as_live_approval():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "not a completed quantitative trading system" in html
    assert "PLANNED / UNVERIFIED" in html
    assert "LIVE TRADING" in html

def test_backup_dashboard_is_read_only_and_promises_no_resume():
    page = DASHBOARD.read_text(encoding='utf-8')
    assert 'id="backup-status"' in page
    assert 'id="backup-jobs"' in page
    assert 'AUTO-RESUME' in page and 'DISABLED' in page
    assert 'value.backup_health || {}' in page

def test_dashboard_displays_inert_registered_dag_without_execution_claim():
    page = DASHBOARD.read_text(encoding='utf-8')
    assert 'id="registered-campaigns"' in page
    assert 'id="registered-nodes"' in page
    assert 'without runnable worker permissions' in page


def test_dashboard_displays_parity_as_unverified_not_approved():
    page = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="unverified-parity"' in page
    assert 'id="parity-differences"' in page
    assert "UNVERIFIED PARITY REPORTS" in page
    assert "NOT READY FOR MARKET RUNS" in page


def test_native_vendor_manifest_status_is_not_presented_as_accepted():
    page = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="native-manifests"' in page
    assert 'id="vendor-exports"' in page
    assert "UNVERIFIED NATIVE MANIFESTS" in page
