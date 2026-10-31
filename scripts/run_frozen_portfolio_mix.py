"""Frozen shared-capacity multi-family XAUUSD research runner.

One observed M1 clock and one 1-oz shared position, never a sum of
independently filled strategy P/L curves. Original private Gold ZIP stays local.
All historical periods remain EXPOSED and are NOT independent OOS.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import fingerprint_loaded_m1, load_market
from norisk_quant.fvg import fvg_midpoint_limit_orders
from norisk_quant.liquidity_sweep import SweepSettings, liquidity_sweep_signals
from norisk_quant.liquidity_sweep_m1 import sweep_reclaim_m1_signals
from norisk_quant.portfolio import PortfolioSettings
from norisk_quant.portfolio_unified import (
    run_unified_portfolio, write_unified_portfolio_report,
)

try:
    from scripts import research_batch_orchestrator as batch
    from scripts.generate_quant_research_grid import SOURCE_SHA
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as batch
    from generate_quant_research_grid import SOURCE_SHA

SCHEMA = "NRFX_FROZEN_SHARED_PORTFOLIO_V1"
KINDS = frozenset({"m1-sweep", "tf-sweep", "bos-fib", "fvg"})
M1_DEFAULTS = {
    "lookback": 20, "min_excess_usd": .15, "reclaim_usd": .05,
    "stop_buffer_usd": .10, "reward_risk": 1.5, "max_stop_usd": 20.0,
}
M1_MAP = {
    "sweep_lookback": "lookback", "sweep_min_excess_usd": "min_excess_usd",
    "sweep_reclaim_usd": "reclaim_usd", "sweep_stop_buffer_usd": "stop_buffer_usd",
    "sweep_reward_risk": "reward_risk", "sweep_max_stop_usd": "max_stop_usd",
}
TF_MAP = {
    "tf_sweep_lookback_bars": "lookback_bars",
    "tf_sweep_penetration_usd": "penetration_usd",
    "tf_sweep_stop_buffer_usd": "stop_buffer_usd",
    "tf_sweep_reward_risk": "reward_risk",
    "tf_sweep_min_stop_usd": "min_stop_usd",
    "tf_sweep_max_stop_usd": "max_stop_usd",
}
BOS_MAP = {
    "bos_pivot_left": "pivot_left", "bos_pivot_right": "pivot_right",
    "bos_fib_entry": "fib_entry", "bos_zone_lower": "zone_lower",
    "bos_zone_upper": "zone_upper", "bos_rr": "reward_risk",
    "bos_stop_buffer_usd": "sl_buffer_usd",
    "bos_min_break_usd": "min_break_usd",
    "bos_min_impulse_usd": "min_impulse_usd",
    "bos_expiry_minutes": "expiry_minutes",
    "bos_min_gross_reward_fee_multiple": "min_gross_reward_fee_multiple",
}
FVG_MAP = {
    "fvg_min_gap_usd": "min_gap_usd",
    "fvg_stop_buffer_usd": "stop_buffer_usd",
    "fvg_rr": "reward_to_risk",
    "fvg_expiry_hours": "expiry_hours",
}


def validate_plan(plan: object) -> dict:
    required = {"schema", "dataset", "source_sha256", "engine_commit",
                "start", "end", "exposure_context", "components"}
    if type(plan) is not dict or set(plan) != required or plan["schema"] != SCHEMA:
        raise ValueError("Unexpected frozen shared-portfolio plan")
    if plan["exposure_context"] != "historical_exposed":
        raise ValueError("Shared research cannot claim prospective or OOS evidence")
    if type(plan["dataset"]) is not str or not Path(plan["dataset"]).is_absolute():
        raise ValueError("Private dataset requires absolute local path")
    if plan["source_sha256"] != SOURCE_SHA:
        raise ValueError("Original Gold ZIP SHA256 is not approved")
    if type(plan["engine_commit"]) is not str or not batch.HEX40.fullmatch(plan["engine_commit"]):
        raise ValueError("Full pinned source code commit required")
    if (type(plan["start"]) is not str or type(plan["end"]) is not str):
        raise ValueError("Invalid calendar dates")
    try:
        start, end = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
    except ValueError as exc:
        raise ValueError("Malformed calendar window") from exc
    if (start.isoformat() != plan["start"] or end.isoformat() != plan["end"]
            or not (date(2010,1,1) <= start <= end < date.today())):
        raise ValueError("Research window must be complete historic UTC dates")
    components = plan["components"]
    if type(components) is not list or not 1 <= len(components) <= 8:
        raise ValueError("Require 1..8 explicit component specifications")
    seen = set()
    for item in components:
        if type(item) is not dict or set(item) != {"strategy", "timeframe", "parameters"}:
            raise ValueError("Unknown shared research component fields")
        if type(item["strategy"]) is not str or item["strategy"] not in KINDS:
            raise ValueError("Unsupported shared research strategy")
        if type(item["timeframe"]) is not str:
            raise ValueError("Research timeframe must be explicit text")
        identity = item["strategy"], item["timeframe"]
        if identity in seen:
            raise ValueError("Duplicate strategy/timeframe in a shared portfolio")
        seen.add(identity)
        # Reuse the same frozen CLI parameter contract as standalone runs.
        batch.check_spec({
            **item, "execution": "reference", "start": plan["start"], "end": plan["end"]
        })
    return plan


def compose(minutes, plan: dict):
    """Generate candidates causally; shared engine owns every actual fill."""
    signals, orders, resolved = [], [], []
    for component in plan["components"]:
        kind, tf, params = (component["strategy"], component["timeframe"],
                            component["parameters"])
        if kind == "m1-sweep":
            args = {**M1_DEFAULTS, **{M1_MAP[key]: value for key,value in params.items()}}
            signals.extend(sweep_reclaim_m1_signals(minutes, **args))
            details = args
        elif kind == "tf-sweep":
            cfg = SweepSettings(timeframe=tf, **{TF_MAP[k]:v for k,v in params.items()})
            signals.extend(liquidity_sweep_signals(minutes, settings=cfg))
            details = asdict(cfg)
        elif kind == "bos-fib":
            cfg = BosFibSettings(**{BOS_MAP[k]:v for k,v in params.items()})
            orders.extend(bos_fib_limit_orders(minutes, settings=cfg))
            details = asdict(cfg)
        else:
            args = {"timeframe": tf,
                    "min_gap_usd": .5, "stop_buffer_usd": .10,
                    "reward_to_risk": 2.0, "expiry_hours": 20.0}
            args.update({FVG_MAP[k]:v for k,v in params.items()})
            orders.extend(fvg_midpoint_limit_orders(minutes, **args))
            details = args
        resolved.append({"strategy": kind, "timeframe": tf,
                         "resolved_parameters": details})
    # One ounce/position shared by all independent generators; per-strategy
    # aliases remain visible for audit and deterministic contention priority.
    allocation = {candidate.strategy: 1.0 for candidate in [*signals, *orders]}
    if not allocation:
        allocation = {"__no_candidate_signals__": 1.0}  # never trades
    settings = PortfolioSettings(ounces_by_strategy=allocation,
                                 max_open_positions=1, max_total_ounces=1.0,
                                 all_in_cost_per_ounce=.40)
    return signals, orders, settings, resolved


def run_frozen(plan_path: Path, output: Path) -> dict:
    plan = validate_plan(batch.read_strict_json(plan_path))
    source = Path(plan["dataset"])
    if (source.is_symlink() or not source.is_file()
            or batch.file_sha(source) != plan["source_sha256"]):
        raise ValueError("Untrusted original Gold ZIP source fingerprint")
    if batch.checkout_commit() != plan["engine_commit"]:
        raise ValueError("Engine checkout differs from frozen plan commit")
    output = output.absolute()
    if (output.exists() or output.is_symlink() or not output.parent.is_dir()
            or any(p.is_symlink() for p in (output.parent, *output.parent.parents))):
        raise ValueError("Frozen portfolio output must be new and private")
    data = load_market(str(source), plan["start"], plan["end"])
    # A source ZIP/year slice can be present but omit entire calendar
    # months. Reject rather than publish a misleading annual portfolio.
    if not hasattr(data.index, "tz") or data.index.tz is None:
        raise ValueError("Research M1 source requires timezone-aware UTC timestamps")
    observed_months = set(data.index.tz_convert("UTC").strftime("%Y-%m"))
    missing_months = set(batch.expected_months(plan["start"], plan["end"])) - observed_months
    if missing_months:
        raise ValueError("Missing research calendar M1 months: " + ",".join(sorted(missing_months)))
    signals, orders, settings, resolved = compose(data, plan)
    result = run_unified_portfolio(data, signals, orders, settings)
    stage = Path(tempfile.mkdtemp(prefix=".nrfx-portfolio-", dir=output.parent))
    os.chmod(stage, 0o700)
    try:
        summary = write_unified_portfolio_report(result, settings, stage)
        evidence_files = ("trades.csv", "monthly.csv", "weekly.csv",
                          "equity_m1.csv", "summary.json")
        evidence = {
            "schema": SCHEMA,
            "evidence_status": "HISTORICAL_EXPOSED_NOT_INDEPENDENT_OOS",
            "source_archive_sha256": plan["source_sha256"],
            "loaded_m1_bidask_sha256": fingerprint_loaded_m1(data),
            "loaded_m1_rows": len(data),
            "pinned_engine_commit": plan["engine_commit"],
            "plan_sha256": hashlib.sha256(batch.canonical(plan)).hexdigest(),
            "strategy_components": resolved,
            "candidate_market_signals": len(signals),
            "candidate_limit_orders": len(orders),
            "executed_shared_trades": int(len(result.trades)),
            "max_open_positions": 1,
            "max_total_ounces": 1.0,
            "cost_all_in_usd_per_ounce": .40,
            "independent_oos_proven": False,
            "broker_tick_fills_proven": False,
            "source_files": {name: batch.file_sha(stage / name) for name in evidence_files},
            "caveat": ("Synthetic OHLC fills, one shared capacity slot; "
                       "fees $0.40/oz; end-of-data closes artificial. No live approval."),
        }
        (stage / "evidence.json").write_bytes(batch.canonical(evidence)+b"\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Another research process published this output first")
        os.rename(stage, output)
        return {"status": evidence["evidence_status"],
                "trades": summary["trades"],
                "net_pnl_closed": summary["net_pnl_closed"],
                "source_files": evidence["source_files"],
                "output": str(output)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_frozen(args.plan, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
