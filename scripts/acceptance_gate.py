"""Fail-closed, single-command acceptance gate for the CURRENT GitHub checkout.

Run from the repository root after installing the pinned dependencies:
  python -m scripts.acceptance_gate --out /secure/reports/acceptance.json \
    --gold-zip "/secure/Gold data.zip" \
    --reference-root "/secure/nrf_bos_h1_validation" --years 2012

No private market bytes are uploaded. A missing archive is BLOCKED, never PASS.
This does not validate real tick fills or an independent out-of-sample result.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED = {
    "numpy": "2.3.5",
    "pandas": "2.2.3",
    "pyarrow": "18.1.0",
    "pytest": "8.4.2",
}
STEPS = (
    ("git_revision", ["git", "rev-parse", "HEAD"]),
    ("git_clean", ["git", "status", "--porcelain=v1", "--untracked-files=all"]),
    ("compile", [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"]),
    ("pip_check", [sys.executable, "-m", "pip", "check"]),
    ("full_pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("cli_smoke", [sys.executable, "-m", "norisk_quant.cli", "--help"]),
)
MARKET_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"


def check_pins() -> dict:
    observed = {name: importlib.metadata.version(name) for name in PINNED}
    if sys.version_info[:2] != (3, 12) or observed != PINNED:
        raise RuntimeError(
            f"Pinned environment mismatch: Python={sys.version_info[:3]}, "
            f"installed={observed}, expected={PINNED} on Python 3.12"
        )
    return {"python": sys.version.split()[0], "packages": observed}


def command_step(name: str, argv: list[str]) -> dict:
    try:
        result = subprocess.run(
            argv, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=1200, check=False,
        )
        return {
            "name": name, "status": "PASSED" if (result.returncode == 0 and (name != "git_clean" or not result.stdout.strip())) else "FAILED",
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-3000:],
            "stderr_tail": result.stderr[-3000:],
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "FAILED", "error": "Timed out after 1200 seconds"}
    except OSError as exc:
        return {"name": name, "status": "FAILED", "error": str(exc)}


def acceptance(*, gold_zip: Path | None, reference_root: Path | None,
               years: list[int]) -> tuple[dict, int]:
    report = {
        "status": "BLOCKED", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "current_checkout_full_pytest_plus_13_field_archived_replay",
        "private_source_uploaded": False,
        "broker_tick_fill_certified": False,
        "clean_out_of_sample_certified": False,
        "steps": [],
    }
    try:
        if not years or any(type(year) is not int or not 2010 <= year <= 2026 for year in years) or len(set(years)) != len(years):
            raise ValueError("Specify distinct integer years from 2010 through 2026")
        if (gold_zip is None) != (reference_root is None):
            raise ValueError("--gold-zip and --reference-root must be provided together")
        report["environment"] = check_pins()
        report["steps"].append({"name": "pinned_environment", "status": "PASSED"})
        for name, argv in STEPS:
            step = command_step(name, argv)
            report["steps"].append(step)
            if step["status"] != "PASSED":
                report["status"] = "FAILED"
                return report, 1
            if name == "git_revision":
                commit = step.get("stdout_tail", "").strip()
                if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
                    raise ValueError("Cannot identify an exact 40-character Git commit")
                report["git_commit"] = commit
        if gold_zip is None:
            report["status"] = "BLOCKED_PRIVATE_ARCHIVE_AND_REFERENCE_NOT_PROVIDED"
            return report, 2
        if not gold_zip.is_file() or not reference_root.is_dir():
            report["status"] = "BLOCKED_PRIVATE_ARCHIVE_OR_REFERENCE_MISSING"
            return report, 2
        from scripts.verify_bos_h1_parity import verify
        verified = verify(gold_zip, reference_root, years)
        if (
            verified.get("status") != "PASSED"
            or verified.get("source_sha256") != MARKET_SHA256
            or verified.get("fields_per_trade") != 13
            or verified.get("scenarios_verified") != 2 * len(years)
        ):
            raise AssertionError("13-field replay verification contract failed")
        if years == [2012] and verified.get("trades_matched") != 689:
            raise AssertionError("2012 two-variant replay must match exactly 689 trades")
        report["steps"].append({
            "name": "archived_13_field_replay", "status": "PASSED",
            "source_sha256": verified["source_sha256"],
            "years": years, "scenarios_verified": verified["scenarios_verified"],
            "trades_matched": verified["trades_matched"],
            "fields_per_trade": verified["fields_per_trade"],
        })
        # Recheck the exact checkout AFTER pytest and market replay. Otherwise
        # tests/scripts could modify tracked files or create untracked modules
        # after the initial clean check, yet the old commit would be certified.
        final_revision = command_step("git_revision", ["git", "rev-parse", "HEAD"])
        final_revision["name"] = "git_revision_after_replay"
        report["steps"].append(final_revision)
        if (final_revision["status"] != "PASSED"
                or final_revision.get("stdout_tail", "").strip() != report["git_commit"]):
            raise AssertionError("Git HEAD changed during acceptance replay")
        final_clean = command_step(
            "git_clean", ["git", "status", "--porcelain=v1", "--untracked-files=all"]
        )
        final_clean["name"] = "git_clean_after_replay"
        report["steps"].append(final_clean)
        if final_clean["status"] != "PASSED":
            raise AssertionError("Checkout became dirty during acceptance replay")
        report["status"] = "PASSED_RESEARCH_GATE_NOT_BROKER_CERTIFIED"
        return report, 0
    except (Exception,) as exc:
        report["status"] = "FAILED"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        return report, 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path)
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--years", nargs="+", type=int, default=[2012])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result, code = acceptance(
        gold_zip=args.gold_zip, reference_root=args.reference_root,
        years=args.years,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "report": str(args.out)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
