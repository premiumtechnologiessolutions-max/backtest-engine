"""Offline native AI Quant Lab V4 Nova export -> canonical paused research queue."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os

import pytest

from norisk_quant.research_control_plane import ResearchQueue
from scripts.import_aiquantlab_hypothesis import main

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)


def nova():
    return {
        "hypothesis_id": "hypothesis_42",
        "campaign_id": "campaign_42",
        "proposed_by": "nova",
        "strategy_name": "kalman_adaptive_trend",
        "parameters": {"lookback": 20, "threshold": 0.25},
        "statement": "A stable latent price slope might predict continuation.",
        "economic_rationale": "Slow trading response can create measurable slope persistence.",
        "falsification_criteria": [
            "No independent positive test effect",
            "Too much cost sensitivity",
            "No stability across regimes",
        ],
        "compatible_regimes": ["trending_up"],
        "parameters_locked_before_test": True,
        "created_at": "2026-10-30T00:00:00Z",
    }


def context():
    return {
        "asset": "XAUUSD",
        "dataset_sha256": "a"*64,
        "engine_commit": "b"*40,
        "aiquantlab_commit": "c"*40,
        "timeframe": "M1",
        "window_start_utc": "2025-01-01T00:00:00Z",
        "window_end_exclusive_utc": "2025-07-01T00:00:00Z",
        "quantity_ounces": 1.0,
        "fee_all_in_per_ounce": 0.4,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }


def inputs(tmp_path):
    hp, cp, db = (tmp_path / "hypothesis.json",
                  tmp_path / "context.json", tmp_path / "private_research.sqlite3")
    hp.write_text(json.dumps(nova()), encoding="utf-8")
    cp.write_text(json.dumps(context()), encoding="utf-8")
    return hp, cp, db


def args(hp, cp, db):
    return ["--hypothesis", str(hp), "--context", str(cp), "--queue-db", str(db)]


def test_actual_v4_hypothesis_shape_is_queued_paused_not_executed(tmp_path, capsys):
    hp, cp, db = inputs(tmp_path)
    assert main(args(hp,cp,db), now=NOW) == 0
    display = json.loads(capsys.readouterr().out)
    assert display["source_agent"] == "nova"
    assert display["execution"] == "NONE"
    assert display["paused"] is True
    assert display["profitability_verified"] is False
    assert display["risk_approved"] is False
    assert display["source_authentication"] == "NOT_VERIFIED"
    record = ResearchQueue(db).status(display["experiment_id"])
    assert record["state"] == "queued"
    assert record["research_only"] is True


def test_duplicate_exports_are_deduped_across_restart(tmp_path, capsys):
    hp, cp, db = inputs(tmp_path)
    main(args(hp,cp,db),now=NOW)
    first = json.loads(capsys.readouterr().out)["experiment_id"]
    main(args(hp,cp,db),now=NOW)
    second = json.loads(capsys.readouterr().out)["experiment_id"]
    assert first == second
    queue = ResearchQueue(db)
    assert queue.counts()["queued"] == 1
    assert len(queue.audit(first)) == 1


def test_exported_hypothesis_comments_and_secret_context_are_not_logged(tmp_path, capsys):
    hp, cp, db = inputs(tmp_path)
    row = nova()
    row["economic_rationale"] = "private alpha observation " + "x"*40
    hp.write_text(json.dumps(row), encoding="utf-8")
    main(args(hp,cp,db),now=NOW)
    public = capsys.readouterr().out
    assert row["economic_rationale"] not in public
    assert "kalman_adaptive_trend" not in public
    assert "lookback" not in public
    assert "USDJPY" not in public


@pytest.mark.parametrize("kind", [
    "extra_field", "unsafe_nested_code", "bad_source", "live",
    "unknown_broker", "null_nan", "float_overflow", "duplicate_json",
])
def test_invalid_source_or_untrusted_directives_are_rejected_without_db(tmp_path, capsys, kind):
    hp, cp, db = inputs(tmp_path)
    row, ctx = nova(), context()
    if kind == "extra_field":
        row["profit_usd"] = 1e10
    elif kind == "unsafe_nested_code":
        row["parameters"] = {"lookback": {"command": "order_send"}}
    elif kind == "bad_source":
        ctx["dataset_sha256"] = "source-uncertified"
    elif kind == "live":
        ctx["exposure_context"] = "future_prospective"
    elif kind == "unknown_broker":
        ctx["mt5_password"] = "verysecret"
    elif kind == "null_nan":
        hp.write_text(json.dumps(row).replace('"threshold": 0.25', '"threshold": NaN'), encoding="utf-8")
    elif kind == "float_overflow":
        hp.write_text(json.dumps(row).replace('"threshold": 0.25', '"threshold": 1e999'), encoding="utf-8")
    elif kind == "duplicate_json":
        hp.write_text('{"hypothesis_id":"safe","hypothesis_id":"forged"}', encoding="utf-8")
    if kind in ("extra_field", "unsafe_nested_code"):
        hp.write_text(json.dumps(row), encoding="utf-8")
    if kind in ("bad_source", "live", "unknown_broker"):
        cp.write_text(json.dumps(ctx), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(args(hp,cp,db),now=NOW)
    assert exc.value.code == 2
    logs = capsys.readouterr()
    assert "verysecret" not in logs.err
    assert "order_send" not in logs.err
    assert "forged" not in logs.err
    assert not db.exists()


def test_symlink_export_is_rejected_before_queue_mutation(tmp_path):
    hp, cp, db = inputs(tmp_path)
    link = tmp_path / "link-hypothesis.json"
    try:
        link.symlink_to(hp)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink unavailable")
    with pytest.raises(SystemExit) as exc:
        main(args(link,cp,db),now=NOW)
    assert exc.value.code == 2
    assert not db.exists()


def test_reject_oversized_ai_record_without_partial_db(tmp_path):
    hp, cp, db = inputs(tmp_path)
    hp.write_bytes(b"x"*17000)
    with pytest.raises(SystemExit) as exc:
        main(args(hp,cp,db),now=NOW)
    assert exc.value.code == 2
    assert not db.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_private_queue_file_not_world_readable(tmp_path, capsys):
    hp, cp, db = inputs(tmp_path)
    main(args(hp,cp,db),now=NOW)
    capsys.readouterr()
    assert db.stat().st_mode & 0o077 == 0
