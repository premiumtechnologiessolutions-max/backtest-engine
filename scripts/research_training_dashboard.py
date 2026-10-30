"""Offline private HTML monitoring/comparison for immutable training evidence.

No web server, no market data export, no independent OOS assertion.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import tempfile

from norisk_quant.research_candidate_memory import select_training_memory
from scripts.materialize_arithmetic_generation import _load_strict
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA


def read_evidence(root: Path) -> list[dict]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Research root must be a real directory")
    folders = sorted(root.glob("generation_*"))
    if not folders:
        raise ValueError("No research generation directories")
    generations = []
    for folder in folders:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Unsafe research generation directory")
        path = folder / "next_training_input.json"
        sidecar = folder / "next_training_input.json.evidence.json"
        if not path.exists() or not sidecar.exists():
            generations.append({"generation": folder.name,
                                "status": "INCOMPLETE_NOT_CERTIFIED", "items": []})
            continue
        if (path.is_symlink() or sidecar.is_symlink()
                or path.stat().st_size > 16 * 1024 * 1024
                or sidecar.stat().st_size > 16 * 1024 * 1024):
            raise ValueError("Unsafe training feedback evidence")
        source, digest = _load_strict(path)
        proof, _ = _load_strict(sidecar)
        if (type(source) is not dict or type(proof) is not dict
                or source.get("schema") != "NRFX_ARITHMETIC_TRAINING_INPUT_V1"
                or proof.get("schema") != "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1"
                or proof.get("training_only") is not True
                or proof.get("independent_oos_proven") is not False
                or proof.get("live_trading_authorized") is not False
                or proof.get("original_archive_sha256") != SOURCE_SHA
                or proof.get("next_input_sha256") != digest
                or source.get("years") != proof.get("training_years")
                or type(source.get("candidates")) is not list
                or type(proof.get("evaluated_formulas")) is not int
                or type(proof.get("complete_formula_year_pairs")) is not int
                or proof["complete_formula_year_pairs"] !=
                proof["evaluated_formulas"] * len(source["years"])):
            raise ValueError("Frozen research evidence mismatch")
        ranked = select_training_memory(
            source["candidates"], tuple(source["years"]), limit=128)
        generations.append({
            "generation": folder.name, "status": "TRAINING_FEEDBACK_VERIFIED_NOT_OOS",
            "items": ranked["selected"], "candidate_count": ranked["active_size"],
            "evaluated_formulas": proof["evaluated_formulas"],
            "formula_year_pairs": proof["complete_formula_year_pairs"],
            "input_sha256": digest,
            "source_sha256": SOURCE_SHA,
        })
    return generations


def render_html(generations: list[dict]) -> str:
    panels, rows = [], []
    for generation in generations:
        name = escape(generation["generation"])
        count = generation.get("candidate_count", "—")
        panels.append(f'<div class="card"><small>{name}</small><h2>{count}</h2>'
                      f'<p>{escape(generation["status"])}</p></div>')
        for item in generation["items"]:
            net = item["net_usd_per_oz"]
            reasons = ", ".join(item["failure_reasons"])
            rows.append("<tr>" + "".join((
                f"<td>{name}</td>",
                f'<td title="{escape(item["identity"])}">{escape(item["identity"][:12])}</td>',
                f'<td>{item["training_score"]:.3f}</td>',
                f'<td class="{"gain" if net > 0 else "loss"}">{net:+.2f}</td>',
                f'<td>{item["positive_months"]}/{item["total_months"]}</td>',
                f'<td>{item["max_month_end_drawdown_usd_per_oz"]:.2f}</td>',
                f'<td>{escape(reasons)}</td>',
            )) + "</tr>")
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>No Risk FX | Research</title>
<style>body{background:#081425;color:#e8eef8;font:15px system-ui;margin:0}main{max-width:1250px;margin:auto;padding:36px 22px}
h1{font-size:32px}h2{font-size:32px;color:#dbc080;margin:6px 0}.cards{display:flex;flex-wrap:wrap;gap:16px;margin:22px 0}
.card{min-width:220px;flex:1;border:1px solid #36465d;border-radius:12px;background:#13243b;padding:20px}
small{color:#d8be81;letter-spacing:.13em}.warn{border-left:3px solid #d8b46f;padding:15px;background:#192a40}
p{color:#a7b7cb}.scroll{max-height:650px;overflow:auto;border:1px solid #314157;border-radius:10px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}
td,th{padding:13px;text-align:left;border-bottom:1px solid #2f4159}th{position:sticky;top:0;background:#172a42;color:#e4c384}
.gain{color:#8ae4b2}.loss{color:#fba2a2}input{padding:11px;background:#13243b;color:#fff;border:1px solid #415674;border-radius:8px;width:min(480px,85%);margin:10px 0 20px}
</style></head><body><main><small>NO RISK FX / QUANT LAB</small>
<h1>Research Evidence & Strategy Comparison</h1>
<div class="warn"><b>TRAINING ONLY — NOT INDEPENDENT OOS</b><p>Historical scores do not prove future profitability or authorize live execution.</p></div>
<section class="cards">""" + "".join(panels) + """</section><h2 style="font-size:22px">Strategy comparison</h2>
<p>Net USD/oz after canonical $0.40/oz per completed trade; historical month-end risk.</p>
<input id="search" type="search" placeholder="Filter strategies and failure reasons" aria-label="Filter">
<div class="scroll"><table id="runs"><thead><tr><th>Generation</th><th>Formula ID</th><th>Train score</th><th>Net USD/oz</th><th>Positive months</th><th>Month-end drawdown</th><th>Research diagnostics</th></tr></thead>
<tbody>""" + "".join(rows) + """</tbody></table></div>
<p>Read-only, private, static HTML. Immutable feedback SHA checked; no raw quotes or independent holdout.</p>
<script>document.getElementById('search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();for(const r of document.querySelectorAll('#runs tbody tr'))r.hidden=!r.textContent.toLowerCase().includes(q)})</script>
</main></body></html>""")


def build_dashboard(root: Path, output: Path) -> dict:
    generations = read_evidence(root)
    if output.is_symlink() or not output.parent.is_dir() or output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Dashboard output must be outside private research evidence")
    if any((parent / ".git").exists() for parent in (output.parent, *output.parent.parents)):
        raise ValueError("Private dashboard must remain outside Git")
    data = render_html(generations).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".nrfx_dashboard_", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, output)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"generations": len(generations),
            "verified_generations": sum(g["status"].startswith("TRAINING_FEEDBACK")
                                        for g in generations),
            "comparison_rows": sum(len(g["items"]) for g in generations),
            "sha256": sha256(data).hexdigest(),
            "independent_oos_proven": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_dashboard(args.runs, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
