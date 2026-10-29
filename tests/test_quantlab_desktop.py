"""Offline local app tests; fake source bytes never count as original Gold data."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import threading

import pytest

from scripts import quantlab_desktop as app


def fake_spec(year=2012):
    return {"year": year, "strategy": "ema", "timeframe": "M15",
            "execution": "fast", "grid": {"fast": [8, 9], "slow": [21], "rr": [1.5, 2.0]}}


@pytest.fixture
def hub(tmp_path, monkeypatch):
    source = tmp_path / "fake-original.zip"
    source.write_bytes(b"THIS IS NOT REAL HISTORICAL GOLD")
    actual = app.lab.file_sha
    monkeypatch.setattr(app.lab, "file_sha", lambda p: app.SOURCE_SHA if Path(p) == source else actual(p))
    monkeypatch.setattr(app.lab, "checkout_commit", lambda: "a" * 40)
    h = app.ResearchHub(tmp_path / "workspace")
    assert not h.status()["source_configured"]
    assert h.configure(str(source))["configured"]
    return h


def test_original_source_is_not_accepted_without_sha(tmp_path):
    file = tmp_path / "fake.zip"
    file.write_bytes(b"fake")
    h = app.ResearchHub(tmp_path / "state")
    with pytest.raises(ValueError, match="fingerprint"):
        h.configure(str(file))
    assert not h.config_path.exists()


def test_preview_does_not_publish_plan_or_run(hub):
    d = hub.preview(fake_spec())
    assert d["status"] == "DEFINED_ONLY_NO_BACKTEST"
    assert d["defined_jobs"] == 4
    assert hub.list_plans() == []
    assert hub.list_runs() == []


def test_freeze_is_immutable_and_idempotent(hub):
    one = hub.freeze(fake_spec())
    two = hub.freeze(fake_spec())
    assert one == two
    assert len(hub.list_plans()) == 1
    plan = hub._plan(one["plan_id"])
    assert plan["exposure_context"] == "historical_exposed"
    assert plan["source_sha256"] == app.SOURCE_SHA
    assert plan["engine_commit"] == "a" * 40
    assert plan["grids"][0]["strategy"] == "ema"
    assert not (hub.runs / one["plan_id"]).exists()
    original = hub.plans / (one["plan_id"] + ".json")
    original.write_text(original.read_text().replace("ema", "fvg"))
    with pytest.raises(ValueError, match="changed|Unsupported|mismatch|Unexpected"):
        hub._plan(one["plan_id"])


@pytest.mark.parametrize("change", [
    {"year": 2026}, {"year": True}, {"year": 2011.0},
    {"strategy": "not-in-engine"}, {"timeframe": ["M15"]},
    {"grid": {"fast": [True]}}, {"grid": {"fast": [float("nan")]}},
    {"grid": {"fast": []}}, {"grid": {"fast": [8, 8]}},
    {"grid": {"fast": [9], "slow": [9]}},
    {"execution": "limit-fast"},
])
def test_unsafe_or_duplicate_grids_fail_closed(hub, change):
    body = fake_spec()
    body.update(change)
    with pytest.raises(ValueError):
        hub.preview(body)


def test_workspaces_are_owner_private_and_refuse_symlink(tmp_path):
    h = app.ResearchHub(tmp_path / "new")
    if os.name == "posix":
        for d in (h.root, h.plans, h.runs):
            assert d.stat().st_mode & 0o077 == 0
    unsafe = tmp_path / "link"
    unsafe.symlink_to(h.root)
    with pytest.raises(ValueError, match="symlink"):
        app.ResearchHub(unsafe / "else")


def test_invalid_session_id_and_wrong_plan_fail_closed(hub):
    with pytest.raises(ValueError):
        hub._plan("../somewhere")
    with pytest.raises(ValueError):
        hub._plan("F" * 64)
    with pytest.raises(ValueError):
        hub.start("a" * 64, 0)


def test_budgeted_worker_serializes_real_runner_invocations(hub, monkeypatch):
    import time
    plan_id = hub.freeze(fake_spec())["plan_id"]
    enter = threading.Event()
    release = threading.Event()
    calls = []
    def fake_runner(plan, output, *, max_jobs, recover_verified_orphans):
        calls.append((plan["source_sha256"], output.name, max_jobs, recover_verified_orphans))
        enter.set()
        assert release.wait(5)
        return {"status": "SYNTHETIC_TEST_DONE"}
    monkeypatch.setattr(app.lab, "run_plan", fake_runner)
    try:
        answer = hub.start(plan_id, 5)
        assert answer["requested_job_budget"] == 5
        assert enter.wait(2)
        assert hub.status()["active_run"] == plan_id
        with pytest.raises(ValueError, match="active"):
            hub.start(plan_id, 5)
    finally:
        release.set()
        hub._thread.join(5)
    assert calls == [(app.SOURCE_SHA, plan_id, 5, False)]
    assert hub.status()["active_run"] is None


def test_worker_errors_visible_and_recoverable(hub, monkeypatch):
    plan_id = hub.freeze(fake_spec())["plan_id"]
    def fail(*a, **k):
        raise RuntimeError("test-only failure")
    monkeypatch.setattr(app.lab, "run_plan", fail)
    hub.start(plan_id, 1)
    hub._thread.join(2)
    assert "RuntimeError" in hub.run_summary(plan_id)["last_error"]
    monkeypatch.setattr(app.lab, "run_plan", lambda *a, **k: None)
    hub.start(plan_id, 1, recover=True)
    hub._thread.join(2)
    assert hub.run_summary(plan_id)["last_error"] is None


def test_run_results_report_recorded_not_reaudited(hub):
    ident = hub.freeze(fake_spec())["plan_id"]
    folder = app.private_dir(hub.runs / ident)
    plan = hub._plan(ident)
    jobs, _ = app.lab.expand(plan)
    manifest = {"schema": app.lab.SCHEMA, "plan_sha256": ident,
                "source_sha256": app.SOURCE_SHA,
                "engine_commit": "a" * 40,
                "results": {jobs[0]["id"]: {"status": app.lab.PASSED, "trades": 8,
                                             "net_pnl": -3.2, "positive_months": 0,
                                             "months_observed": 12}}}
    app.put_once(folder / "batch_manifest.json", manifest)
    data = hub.run_results(ident)
    assert data["recorded_reconciled_unverified"] == 1
    assert data["jobs"][0]["trades"] == 8
    assert data["evidence_status"].startswith("RECORDED_NOT_REAUDITED")


def server(hub, ui_file):
    srv = app.ConsoleServer(("127.0.0.1", 0), hub, ui_file, "private-test-token")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread


def http(srv, method, path, *, token=None, body=None, origin=None, host=None):
    conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=6)
    headers = {"Host": host or f"127.0.0.1:{srv.server_port}"}
    if token is not None:
        headers["X-NRFX-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body)
    conn.request(method, path, body=body, headers=headers)
    res = conn.getresponse()
    payload = res.read()
    status = res.status
    conn.close()
    return status, payload


def test_loopback_http_token_origin_and_plan_creation(hub):
    ui_file = Path(app.__file__).with_name("quantlab_desktop_ui.html")
    srv, thread = server(hub, ui_file)
    try:
        code, page = http(srv, "GET", "/")
        assert code == 200
        assert b"QUANT RESEARCH LAB" in page
        code, _ = http(srv, "GET", "/api/status")
        assert code == 403
        code, _ = http(srv, "GET", "/api/status", token="wrong")
        assert code == 403
        code, _ = http(srv, "GET", "/api/status", token="private-test-token", host="evil.example")
        assert code == 403
        code, _ = http(srv, "POST", "/api/freeze", token="private-test-token",
                       body=fake_spec(), origin="https://evil.example")
        assert code == 403
        code, raw = http(srv, "POST", "/api/preview", token="private-test-token", body=fake_spec())
        assert code == 200
        assert json.loads(raw)["defined_jobs"] == 4
        code, raw = http(srv, "POST", "/api/freeze", token="private-test-token", body=fake_spec())
        assert code == 200
        assert json.loads(raw)["status"] == "FROZEN_PLAN_NOT_EXECUTED"
        code, raw = http(srv, "GET", "/api/plans", token="private-test-token")
        assert code == 200
        assert len(json.loads(raw)) == 1
        code, _ = http(srv, "GET", "/favicon.ico")
        assert code == 404
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(4)


def test_reader_rejects_oversized_post(hub):
    ui_file = Path(app.__file__).with_name("quantlab_desktop_ui.html")
    srv, thread = server(hub, ui_file)
    try:
        code, raw = http(srv, "POST", "/api/preview", token="private-test-token",
                         body={"junk": "x" * (app.MAX_BODY + 50)})
        assert code == 400
        assert "Request exceeds" in raw.decode()
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(4)


@pytest.mark.parametrize("raw", [
    b'{"year":2012,"year":2013}',
    b'{"year":2012,"grid":{"fast":[8],"fast":[9]}}',
    b'{"year":2012,"grid":{"fast":[1e999]}}',
    b'{"year":2012,"grid":{"fast":[-1e999]}}',
    b'{"year":2012,"grid":{"fast":[NaN]}}',
    b'{"year":2012,"grid":{"fast":[Infinity]}}',
    b'\xff',
])
def test_http_rejects_ambiguous_or_nonfinite_request_json(hub, raw):
    ui_file = Path(app.__file__).with_name("quantlab_desktop_ui.html")
    srv, thread = server(hub, ui_file)
    try:
        conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=6)
        conn.request("POST", "/api/freeze", body=raw, headers={
            "Host": f"127.0.0.1:{srv.server_port}",
            "X-NRFX-Token": "private-test-token",
            "Content-Type": "application/json",
        })
        res = conn.getresponse()
        body = res.read()
        assert res.status == 400, body
        conn.close()
        assert hub.list_plans() == []
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(4)


def test_http_strict_parser_accepts_valid_nested_finite_json(hub):
    ui_file = Path(app.__file__).with_name("quantlab_desktop_ui.html")
    srv, thread = server(hub, ui_file)
    try:
        code, raw = http(srv, "POST", "/api/freeze", token="private-test-token",
                         body=fake_spec())
        assert code == 200, raw
        assert json.loads(raw)["defined_jobs"] == 4
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(4)
