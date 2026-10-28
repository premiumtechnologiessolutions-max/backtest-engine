"""Private, read-only monthly Quant Terminal from a freshly re-audited frozen batch.

Never accepts a precomputed scorecard JSON as evidence. The CLI calls the
canonical scorecard verifier against the private source on the exact checkout.
No execution, live prices, network access, or broker integration.
"""
from __future__ import annotations

import argparse
from html import escape
import math
from pathlib import Path
import re

try:
    from scripts import research_batch_monthly_scorecard as audit
    from scripts import research_batch_orchestrator as lab
    from scripts.research_terminal_export import write_private_html
except ModuleNotFoundError as exc:  # direct invocation from repository root
    if exc.name != "scripts":
        raise
    import research_batch_monthly_scorecard as audit
    import research_batch_orchestrator as lab
    from research_terminal_export import write_private_html

MONTH = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])\Z")
JOB = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _number(value: object, name: str, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Invalid verified " + name)
    if nonnegative and value < 0:
        raise ValueError("Negative verified " + name)
    return float(value)


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid verified " + name)
    return value


def _money(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+,.2f}"


def _check(report: dict) -> list[dict]:
    """Defend the renderer even if an upstream caller passes forged objects."""
    if (type(report) is not dict
            or report.get("status") != "RE_AUDITED_HISTORICAL_STANDALONE_NOT_OOS_NOT_APPROVED"
            or report.get("source_sha256_verified_locally") is not True
            or type(report.get("plan_sha256")) is not str
            or not HEX64.fullmatch(report["plan_sha256"])
            or report.get("independent_hypotheses") is not None
            or report.get("shared_capacity_portfolio_net_usd_per_oz") is not None
            or _count(report.get("prospective_months"), "prospective months") != 0
            or _count(report.get("approved_strategies"), "approved strategies") != 0):
        raise ValueError("Unverified or misleading monthly research report")
    jobs = report.get("jobs")
    if type(jobs) is not list or len(jobs) > 500:
        raise ValueError("Invalid verified job collection")
    completed = _count(report.get("reconciled_executed_jobs"), "executed jobs")
    defined = _count(report.get("defined_parameter_jobs"), "defined jobs")
    missing = _count(report.get("not_executed_jobs"), "missing jobs")
    pinned = _count(report.get("hash_pinned_m1_jobs"), "pinned jobs")
    unpinned = _count(report.get("unverified_floating_m1_jobs"), "unpinned jobs")
    if completed != len(jobs) or defined != completed + missing or pinned + unpinned != completed:
        raise ValueError("Inconsistent verified job accounting")
    seen = set()
    pinned_actual = 0
    for job in jobs:
        if type(job) is not dict or job.get("status") != "HISTORICAL_EXPOSED_STANDALONE_NOT_APPROVED":
            raise ValueError("Unverified job status")
        ident = job.get("id")
        if type(ident) is not str or not JOB.fullmatch(ident) or ident in seen:
            raise ValueError("Invalid or duplicate verified job ID")
        seen.add(ident)
        months = job.get("monthly")
        if type(months) is not list or not months:
            raise ValueError("Missing verified monthly ledger")
        if _count(job.get("months_observed"), "observed months") != len(months):
            raise ValueError("Inconsistent verified monthly count")
        _count(job.get("positive_months"), "positive months")
        total_trades = _count(job.get("trades"), "trades")
        fees = _number(job.get("all_in_fees_usd_per_oz"), "fees", nonnegative=True)
        net = _number(job.get("net_usd_per_oz"), "net")
        worst = job.get("worst_month_utc")
        worst_value = _number(job.get("worst_month_net_usd_per_oz"), "worst month")
        if job.get("shared_capacity_verified") is not False or job.get("clean_prospective_oos") is not False:
            raise ValueError("Uncertified portfolio or OOS claim")
        observed = set()
        previous = ""
        count_trades = 0
        count_positive = 0
        sum_fees = 0.0
        sum_net = 0.0
        minimum = None
        pinned_months = 0
        for month in months:
            if type(month) is not dict:
                raise ValueError("Malformed verified month")
            label = month.get("month_utc")
            if type(label) is not str or not MONTH.fullmatch(label) or label <= previous or label in observed:
                raise ValueError("Invalid or unordered verified month")
            observed.add(label)
            previous = label
            pnl = _number(month.get("net_usd_per_oz"), "monthly net")
            monthly_fees = _number(month.get("all_in_fees_usd_per_oz"), "monthly fees", nonnegative=True)
            count_trades += _count(month.get("trades"), "monthly trades")
            _count(month.get("observed_m1_samples"), "M1 samples")
            dd = month.get("max_observed_m1_global_peak_drawdown_usd_per_oz")
            gaps = month.get("observed_m1_gap_events_from_prior_mark")
            if (dd is None) != (gaps is None):
                raise ValueError("Incomplete pinned monthly floating-risk evidence")
            if dd is not None:
                _number(dd, "floating drawdown", nonnegative=True)
                _count(gaps, "M1 gaps")
                pinned_months += 1
            count_positive += pnl > 0
            sum_net += pnl
            sum_fees += monthly_fees
            if minimum is None or pnl < minimum[1]:
                minimum = (label, pnl)
        if (count_trades != total_trades or count_positive != job["positive_months"]
                or not math.isclose(sum_net, net, abs_tol=1e-5, rel_tol=0)
                or not math.isclose(sum_fees, fees, abs_tol=1e-5, rel_tol=0)
                or minimum[0] != worst
                or not math.isclose(minimum[1], worst_value, abs_tol=1e-5, rel_tol=0)
                or pinned_months not in (0, len(months))):
            raise ValueError("Verified monthly ledger totals or worst month mismatch")
        dd = job.get("observed_m1_floating_drawdown_usd_per_oz")
        if pinned_months:
            _number(dd, "job floating drawdown", nonnegative=True)
            if not any(math.isclose(dd, m["max_observed_m1_global_peak_drawdown_usd_per_oz"],
                                    abs_tol=1e-5, rel_tol=0) for m in months):
                raise ValueError("Pinned floating drawdown missing from months")
            pinned_actual += 1
        elif dd is not None:
            raise ValueError("Unpinned floating drawdown must be N/A")
    if pinned_actual != pinned:
        raise ValueError("Pinned job count mismatch")
    return jobs


def render_verified_monthly_html(report: dict) -> str:
    """Accessible offline HTML with no invented monthly outcomes or JS data blobs."""
    jobs = _check(report)
    cards = []
    rows = []
    for job in jobs:
        ident = escape(job["id"], quote=True)
        worst = escape(job["worst_month_utc"])
        dd = job["observed_m1_floating_drawdown_usd_per_oz"]
        cards.append(
            '<article class="card"><h2>' + ident + '</h2>'
            '<p>Historical standalone · NOT APPROVED · shared capacity N/A</p>'
            '<div class="facts"><span>Net: <b>' + _money(job["net_usd_per_oz"]) + '</b></span>'
            '<span>All-in fees: <b>' + f'{job["all_in_fees_usd_per_oz"]:,.2f}' + '</b></span>'
            '<span>Positive months: <b>' + str(job["positive_months"]) + '/'
            + str(job["months_observed"]) + '</b></span>'
            '<span>Worst: <b>' + worst + ' · ' + _money(job["worst_month_net_usd_per_oz"]) + '</b></span>'
            '<span>Observed M1 DD: <b>' + _money(dd) + '</b></span></div></article>')
        for month in job["monthly"]:
            label = escape(month["month_utc"], quote=True)
            rows.append(
                '<tr data-job="' + ident + '" data-month="' + label + '"><th scope="row">'
                + ident + '</th><td>' + label + '</td><td class="num">'
                + _money(month["net_usd_per_oz"]) + '</td><td class="num">'
                + str(month["trades"]) + '</td><td class="num">'
                + f'{month["all_in_fees_usd_per_oz"]:,.2f}' + '</td><td class="num">'
                + str(month["observed_m1_samples"]) + '</td><td class="num">'
                + _money(month["max_observed_m1_global_peak_drawdown_usd_per_oz"])
                + '</td><td class="num">'
                + (str(month["observed_m1_gap_events_from_prior_mark"])
                   if month["observed_m1_gap_events_from_prior_mark"] is not None else "N/A")
                + '</td></tr>')
    options = ''.join('<option value="' + escape(j["id"], quote=True) + '">'
                      + escape(j["id"]) + '</option>' for j in jobs)
    content = ''.join(cards) if cards else '<p>No executed source-verified jobs in this frozen batch.</p>'
    table_rows = ''.join(rows)
    digest = escape(report["plan_sha256"])
    return f'''<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>NO RISK FX · Verified Monthly Research</title>
<style>
:root{{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#081121;color:#edf3fa}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at 80% 0%,#213a58,#081121 55%);min-height:100vh}}
main{{max-width:1500px;margin:auto;padding:clamp(18px,3vw,44px)}}a{{color:#eac583}}
header{{border-bottom:1px solid #32445a;padding-bottom:24px}}.brand{{color:#eac583;letter-spacing:.2em;font-size:12px;font-weight:800}}
h1{{font-size:clamp(27px,4vw,48px);margin:12px 0}}h2{{font-size:16px;margin:0 0 9px}}
.sub,.card p{{color:#b9c9da;font-size:13px;line-height:1.7}}.warning{{background:#2b261f;border:1px solid #937f5d;color:#f2dfbd;border-radius:12px;padding:15px;margin:24px 0;line-height:1.7}}
.summary{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}.badge{{border:1px solid #53667c;border-radius:99px;padding:9px 13px;font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:14px;margin:20px 0}}
.card{{background:#13243a;border:1px solid #31465c;border-radius:15px;padding:20px;min-width:0;overflow-wrap:anywhere}}
.facts{{display:grid;gap:8px;font-size:13px}}.facts b{{color:#eac583}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:20px 0}}
button,select,input{{font:inherit;background:#17283d;color:#f1f5fa;border:1px solid #56708b;border-radius:8px;padding:10px}}
button{{cursor:pointer}}button:focus-visible,select:focus-visible,input:focus-visible{{outline:3px solid #eac583;outline-offset:3px}}
.tablewrap{{overflow-x:auto;border:1px solid #32465e;border-radius:13px}}table{{border-collapse:collapse;width:100%;min-width:930px}}
th,td{{padding:13px 12px;text-align:start;border-bottom:1px solid #31465a;font-size:12px}}thead{{background:#1b3049}}
.num{{font-variant-numeric:tabular-nums;text-align:end}}tbody tr:hover{{background:#1c324a}}
footer{{border-top:1px solid #304459;margin-top:30px;padding:20px 0;color:#aabed2;font-size:12px;overflow-wrap:anywhere}}
[hidden]{{display:none!important}}@media(max-width:620px){{main{{padding:16px}}.controls>*{{width:100%}}}}
</style></head><body><main><header><div class="brand">NO RISK FX · QUANT TERMINAL</div>
<h1 data-en="Verified monthly research" data-ar="الأبحاث الشهرية المدقّقة">Verified monthly research</h1>
<p class="sub" data-en="Private original-source re-audit · Historical standalone results only" data-ar="تدقيق محلي للمصدر الأصلي · نتائج تاريخية منفصلة فقط">Private original-source re-audit · Historical standalone results only</p>
<button type="button" id="lang" aria-pressed="false" aria-label="Switch to Arabic">العربية</button></header>
<div class="warning" role="note" data-en="NOT prospective OOS. NOT a shared-capacity portfolio. NOT approved for live trading. Monthly net is exit-booked after the fixed all-in cost. Floating drawdown is N/A unless independently pinned M1 equity is verified. No missing minutes are fabricated."
data-ar="ليست نتائج مستقبلية مستقلة ولا محفظة بسعة مشتركة ولا اعتماداً للتداول الحقيقي. صافي الشهر بعد التكلفة الثابتة ويُسجّل عند إغلاق الصفقة. السحب العائم N/A دون تدقيق بصمات مستقلة لبيانات M1. لا تُنشأ دقائق مفقودة.">NOT prospective OOS. NOT a shared-capacity portfolio. NOT approved for live trading. Monthly net is exit-booked after the fixed all-in cost. Floating drawdown is N/A unless independently pinned M1 equity is verified. No missing minutes are fabricated.</div>
<div class="summary"><span class="badge">{len(jobs)} audited jobs</span>
<span class="badge">{report["not_executed_jobs"]} not executed</span>
<span class="badge">{report["hash_pinned_m1_jobs"]} M1 risk pinned</span>
<span class="badge">0 prospective months · 0 approved</span></div>
<div class="cards">{content}</div>
<h2 data-en="Verified UTC monthly ledger" data-ar="السجل الشهري المدقّق بتوقيت UTC">Verified UTC monthly ledger</h2>
<div class="controls"><label for="jobFilter" data-en="Job" data-ar="التجربة">Job</label>
<select id="jobFilter" aria-label="Filter by job"><option value="">All audited jobs</option>{options}</select>
<label for="monthFilter" data-en="UTC month" data-ar="الشهر UTC">UTC month</label>
<input type="search" id="monthFilter" placeholder="YYYY-MM" aria-label="Filter UTC month">
<span id="visible" role="status" aria-live="polite"></span></div>
<div class="tablewrap"><table><caption>Re-audited monthly results, not future returns</caption><thead><tr>
<th scope="col">Job</th><th scope="col">UTC month</th><th scope="col">Net USD/oz</th>
<th scope="col">Trades</th><th scope="col">Fees USD/oz</th><th scope="col">M1 marks</th>
<th scope="col">Observed floating DD</th><th scope="col">M1 gaps</th>
</tr></thead><tbody id="monthlyRows">{table_rows}</tbody></table></div>
<footer>Plan SHA256: <code>{digest}</code><br>Source and canonical ledger verified locally on the exact checkout.
No raw BID/ASK, network, broker access or trading commands in this HTML.</footer></main>
<script>
(()=>{{"use strict";
const select=document.getElementById("jobFilter"),month=document.getElementById("monthFilter");
const rows=[...document.querySelectorAll("#monthlyRows tr")],status=document.getElementById("visible");
function filter(){{let n=0;for(const row of rows){{const visible=(!select.value||row.dataset.job===select.value)&&row.dataset.month.includes(month.value.trim());row.hidden=!visible;if(visible)n++;}}status.textContent=n+" / "+rows.length+" UTC months";}}
select.addEventListener("change",filter);month.addEventListener("input",filter);filter();
const button=document.getElementById("lang");
button.addEventListener("click",()=>{{const ar=document.documentElement.lang!=="ar";
document.documentElement.lang=ar?"ar":"en";document.documentElement.dir=ar?"rtl":"ltr";
button.textContent=ar?"English":"العربية";button.setAttribute("aria-pressed",String(ar));
button.setAttribute("aria-label",ar?"Switch to English":"Switch to Arabic");
for(const el of document.querySelectorAll("[data-en]"))el.textContent=ar?el.dataset.ar:el.dataset.en;
}});
}})();
</script></body></html>'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Frozen private batch plan")
    parser.add_argument("--batch-output", type=Path, required=True, help="Canonical batch output directory")
    parser.add_argument("--html", type=Path, required=True, help="Private HTML output path")
    parser.add_argument("--equity-pins", type=Path, help="Independently frozen M1 evidence hashes")
    args = parser.parse_args(argv)
    plan = lab.read_strict_json(args.plan)
    pins = lab.read_strict_json(args.equity_pins) if args.equity_pins else None
    verified = audit.scorecard(plan, args.batch_output, equity_pins=pins)
    html = render_verified_monthly_html(verified)
    write_private_html(args.html, html)
    print(f"Re-audited {verified['reconciled_executed_jobs']} historical standalone jobs; "
          f"{verified['hash_pinned_m1_jobs']} M1-pinned; 0 prospective months; 0 approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
