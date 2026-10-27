"""Offline read-only No Risk FX quant research terminal.

Renders audited factory-registry METADATA, never a trading signal. No network,
no private XAUUSD quotes, and no inference that a test is clean OOS.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote

try:
    from scripts.audit_strategy_factory_registry import audit_registry
except ModuleNotFoundError:  # direct script invocation from repository root
    from audit_strategy_factory_registry import audit_registry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "research" / "strategy_factory_registry.json"
SAFE_REPORT = re.compile(r"^(?:docs|research)/[A-Za-z0-9._/-]+$")


def _nonnegative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}: expected nonnegative integer")
    return value


def dashboard_model(registry: dict) -> dict:
    """Reconcile totals before accepting any registry values into the UI."""
    totals = audit_registry(registry)
    rows = []
    for batch in registry["completed_batches"]:
        ident = batch["id"]
        report = batch.get("report")
        if report is not None and (
            type(report) is not str or not SAFE_REPORT.fullmatch(report)
            or ".." in Path(report).parts
        ):
            raise ValueError(f"Unsafe report path: {ident}")
        active = batch.get("active_annual_replays",
                           batch.get("annual_replays_with_filled_trades"))
        if active is None:
            active = 0 if ident == "NRF-FAC-005" else batch.get("completed_annual_replays")
        rows.append({
            "id": str(ident),
            "family": str(batch.get("family", "Not recorded")),
            "status": str(batch.get("status", "UNVERIFIED")),
            "specs": _nonnegative_integer(batch["unique_parameter_specs"], f"{ident} specs"),
            "active_replays": _nonnegative_integer(active, f"{ident} active"),
            "best_positive_months": _nonnegative_integer(
                batch["maximum_positive_months_out_of_24"], f"{ident} months"),
            "passing_24_of_24": _nonnegative_integer(
                batch["configs_24_of_24"], f"{ident} full-month passes"),
            "report": report,
        })
    if sum(row["passing_24_of_24"] for row in rows) != totals["strictly_positive_every_month_in_both_years"]:
        raise ValueError("Monthly pass count is inconsistent")
    return {
        "updated_utc": str(registry.get("updated_utc", "unknown")),
        "research_status": str(registry.get("research_status", "UNVERIFIED")),
        "specifications": totals["distinct_parameter_specs"],
        "annual_replays": totals["yearly_backtests"],
        "families": totals["independent_hypothesis_families"],
        "monthly_observations": totals["exit_booked_monthly_points"],
        "passing_24_of_24": totals["strictly_positive_every_month_in_both_years"],
        "fee": registry["fixed_roundtrip_all_in_fee_usd_per_oz"],
        "rows": rows,
    }


def render_html(model: dict) -> str:
    """A standalone HTML dashboard; all registry-derived text is escaped."""
    esc = lambda item: escape(str(item), quote=True)
    metrics = [
        ("Parameter specifications", model["specifications"]),
        ("Active annual replays", model["annual_replays"]),
        ("Research families", model["families"]),
        ("Passing 24 / 24 months", model["passing_24_of_24"]),
    ]
    cards = "".join(
        '<article class="metric"><span>' + esc(label) + '</span><strong>'
        + format(n, ",") + '</strong></article>'
        for label, n in metrics
    )
    table_rows = []
    for row in model["rows"]:
        evidence = '<span class="muted">Not linked</span>'
        if row["report"]:
            href = ("https://github.com/premiumtechnologiessolutions-max/"
                    "backtest-engine/blob/feat/quant-engine-foundation/"
                    + quote(row["report"], safe="/"))
            evidence = '<a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">Read evidence</a>'
        cells = (
            esc(row["id"]), esc(row["family"]), format(row["specs"], ","),
            format(row["active_replays"], ","),
            str(row["best_positive_months"]) + " / 24", esc(row["status"]), evidence,
        )
        table_rows.append("<tr>" + "".join(
            "<td>" + cell + "</td>" for cell in cells) + "</tr>")
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>No Risk FX Quant Research Terminal</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#081424;color:#eff5ff}
*{box-sizing:border-box}body{margin:0}header{background:#0d1c31;border-bottom:1px solid #29405a;padding:30px clamp(16px,4vw,56px)}
.brand{color:#e5c68c;font-weight:750;letter-spacing:.14em;font-size:13px}
h1{font-size:clamp(24px,3vw,38px);margin:12px 0}p{color:#acbfd4;line-height:1.5}
main{padding:24px clamp(16px,4vw,56px);max-width:1600px;margin:auto}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.metric{background:#13253d;border:1px solid #314862;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:9px}
.metric span{font-size:12px;color:#b5c8dc}.metric strong{font-size:clamp(19px,2.6vw,31px)}
.warning{border-left:4px solid #e1c38a;background:#192738;padding:15px 18px;margin:20px 0;color:#e9dcbf;line-height:1.5}
.toolbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin:28px 0 12px}
input{background:#0f2036;border:1px solid #3b5471;color:white;padding:12px;border-radius:8px;min-width:260px}
.tablewrap{overflow:auto;border:1px solid #314862;border-radius:12px}
table{border-collapse:collapse;width:100%;min-width:1120px}th{text-align:left;font-size:11px;text-transform:uppercase;color:#b1c4dc;background:#182b45}
td,th{padding:12px;border-bottom:1px solid #263b54;vertical-align:top}td{font-size:12px;color:#dae6f5;line-height:1.45}
td:nth-child(2){max-width:365px}td:nth-child(6){font-size:10px;color:#e1c38a;overflow-wrap:anywhere}
a{color:#a4d3ff}.muted,footer{color:#8298b0}footer{padding-top:25px;font-size:12px}
@media(max-width:760px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{padding:12px}.metric strong{font-size:20px}}
</style></head><body>
<header><div class="brand">NO RISK FX / RESEARCH</div><h1>Quant Research Terminal</h1>
<p>OFFLINE · READ ONLY · HISTORICAL &nbsp;|&nbsp; Registry updated: __UPDATED__</p>
<p>Registry research status: __STATUS__</p></header>
<main><div class="metrics">__METRICS__</div>
<div class="warning"><b>Research only:</b> correlated parameter variants are not independently proven strategies.
2012–2013 design years are historically exposed. Metadata arithmetic validation does NOT
prove real fills, independent OOS, future monthly profitability or permission for live trading.
The research uses a fixed $0.40/oz all-in roundtrip cost model.</div>
<div class="toolbar"><h2>Experiment families</h2>
<input type="search" id="filter" placeholder="Filter ID / family / status" aria-label="Filter experiment families">
<span id="count"></span></div>
<div class="tablewrap"><table><thead><tr><th>ID</th><th>Hypothesis</th><th>Specs</th>
<th>Active annual tests</th><th>Best positive months</th><th>Reported status</th><th>Report</th>
</tr></thead><tbody>__ROWS__</tbody></table></div>
<footer>Offline local HTML. No trading connection or external scripts. Evidence links open GitHub only if clicked.</footer>
</main>
<script>
const input=document.getElementById('filter'),rows=[...document.querySelectorAll('tbody tr')],count=document.getElementById('count');
function filterRows(){const s=input.value.toLowerCase().trim();let n=0;
for(const row of rows){const visible=row.textContent.toLowerCase().includes(s);row.hidden=!visible;if(visible)n++;}
count.textContent=n+' / '+rows.length+' families';}
input.addEventListener('input',filterRows);filterRows();
</script></body></html>"""
    return (document.replace("__UPDATED__", esc(model["updated_utc"]))
            .replace("__STATUS__", esc(model["research_status"]))
            .replace("__METRICS__", cards)
            .replace("__ROWS__", "\n".join(table_rows)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "reports" / "research_terminal.html")
    args = parser.parse_args(argv)
    model = dashboard_model(json.loads(args.registry.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(model), encoding="utf-8")
    print(json.dumps({
        "status": "AUDITED_METADATA_ONLY_NOT_OOS_CERTIFIED",
        "html": str(args.out),
        "families": len(model["rows"]),
        "specifications": model["specifications"],
        "passing_24_of_24": model["passing_24_of_24"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
