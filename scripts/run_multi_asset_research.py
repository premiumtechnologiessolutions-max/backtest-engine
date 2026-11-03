"""Offline OANDA-v20 observation -> causal macro context -> robot intent audit.

Never submits OANDA orders. Optional practice FETCH does bounded GET only.
No token, private quote payload, or macro raw source is published to GitHub.
Reports indicate INTENTS, not fills/P&L. Default input is owner-provided JSON.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from norisk_quant.oanda_readonly import fetch_practice_m1, parse_closed_m1
from norisk_quant.causal_market_context import (
    observations_from_json, schedules_from_json,
)
from norisk_quant.robot_research_lab import robots_from_json, evaluate_robots
from scripts.run_quant_research_platform import _safe_private_root


def _read(path: Path, limit: int = 5_000_000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing or unsafe bounded private research JSON")
    def unique(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key in frozen research input")
            result[key] = val
        return result
    def bad_constant(_):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=unique, parse_constant=bad_constant)


def run(args) -> dict:
    robots = robots_from_json(_read(args.robots))
    context = _read(args.context)
    if type(context) is not dict or set(context) != {"observations", "schedules"}:
        raise ValueError("Context requires observations and schedules arrays")
    observations = observations_from_json(context["observations"])
    schedules = schedules_from_json(context["schedules"])
    if args.practice:
        if args.candles is not None or args.start is None or args.end is None:
            raise ValueError("Practice requires start/end and no candles input")
        token = os.environ.get("OANDA_PRACTICE_TOKEN", "")
        by_symbol = {symbol: fetch_practice_m1(
            symbol, args.start, args.end, bearer_token=token)
            for symbol in sorted({r.instrument for r in robots})}
    else:
        if args.candles is None or args.start or args.end:
            raise ValueError("Offline mode requires candles input only")
        raw = _read(args.candles)
        if type(raw) is not dict or set(raw) != {r.instrument for r in robots}:
            raise ValueError("Candles must exactly cover declared robot instruments")
        by_symbol = {symbol: parse_closed_m1(payload, symbol)
                     for symbol, payload in sorted(raw.items())}
    report = evaluate_robots(by_symbol, robots, observations, schedules)
    root = args.out.resolve()
    _safe_private_root(root)
    target = root / "multi_asset_intents.json"
    if target.exists() or target.is_symlink():
        raise ValueError("Immutable research evidence already exists")
    payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
               + "\n").encode()
    fd, tmp = tempfile.mkstemp(prefix=".multi-asset-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists() or target.is_symlink():
            raise ValueError("Immutable evidence raced with another process")
        # Only one process should own this private output root.
        os.link(tmp, target)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"output": str(target), "status": report["status"],
            "intent_count": len(report["intents"]),
            "manifest_sha256": report["manifest_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robots", required=True, type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--candles", type=Path, help="Private OANDA historical BA JSON")
    parser.add_argument("--practice", action="store_true",
                        help="READ ONLY OANDA practice M1 candles using private environment token")
    parser.add_argument("--start", help="UTC window start (practice only)")
    parser.add_argument("--end", help="UTC window end (practice only)")
    parser.add_argument("--out", required=True, type=Path,
                        help="Owner-only, outside-checkout private directory")
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
