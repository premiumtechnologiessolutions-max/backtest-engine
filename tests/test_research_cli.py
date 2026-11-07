import json
import sys

from norisk_quant.cli import main


def test_cli_identify_experiment_is_deterministic(tmp_path, monkeypatch, capsys):
    spec = {
        "dataset_sha256": "a" * 64,
        "engine_commit": "b" * 40,
        "strategy_id": "fvg_h1",
        "parameters": {"displacement_atr": 1, "target_r": 2},
        "timeframe": "H1",
        "window_start_utc": "2012-01-01T00:00:00+00:00",
        "window_end_exclusive_utc": "2019-01-01T00:00:00+00:00",
        "quantity_ounces": 1.0,
    }
    input_file = tmp_path / "spec.json"
    output_file = tmp_path / "identity.json"
    input_file.write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["norisk", "identify-experiment", "--spec", str(input_file),
                      "--out", str(output_file)],
    )
    main()
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert printed == saved
    assert len(saved["experiment_id"]) == 64
    assert not saved["independent_test_proven"]
    assert saved["execution_status"] == "DEFINED_ONLY"


def test_cli_plan_walkforward_explicitly_marks_not_independent(tmp_path, monkeypatch, capsys):
    output_file = tmp_path / "plan.json"
    monkeypatch.setattr(
        sys, "argv", [
            "norisk", "plan-walkforward",
            "--start-year", "2012",
            "--last-year", "2020",
            "--min-training-years", "5",
            "--embargo-days", "7",
            "--out", str(output_file),
        ],
    )
    main()
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert printed["folds"] == 4
    assert saved["validation_status"] == "PLANNED_ONLY_NO_RESULT_IS_INDEPENDENT"
    assert all(not f["evaluation_is_independent"] for f in saved["folds"])
