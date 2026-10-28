"""Opt-in, read-only verified monthly panel for the unified Quant Terminal.

Only source-re-audited canonical batch scorecards may be rendered. The panel
does not load external files, execute strategies, certify OOS, or combine
standalone returns into a shared-capacity portfolio.
"""
from __future__ import annotations

from html import escape

try:
    from scripts.research_batch_verified_monthly_terminal import _check
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_batch_verified_monthly_terminal import _check

MAX_JOBS = 20
MAX_MONTH_ROWS = 2400


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _money(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+,.2f}"


def render_verified_monthly_section(report: dict) -> str:
    """Fail closed before rendering any reported P/L, fees or floating risk."""
    jobs = _check(report)
    if len(jobs) > MAX_JOBS or sum(len(job["monthly"]) for job in jobs) > MAX_MONTH_ROWS:
        raise ValueError("Verified monthly terminal export exceeds bounded UI capacity")

    cards = []
    rows = []
    for job in jobs:
        ident = _e(job["id"])
        worst_three = job["worst_three_complete_calendar_months_net_usd_per_oz"]
        risk = _money(job["observed_m1_floating_drawdown_usd_per_oz"])
        cards.append(
            '<article class="panel"><h3>' + ident + '</h3>'
            '<p class="sub">Historical standalone · NOT APPROVED · shared capacity N/A</p>'
            '<p class="sub">Net USD/oz: <b>' + _money(job["net_usd_per_oz"]) + '</b> · '
            'Positive months: <b>' + str(job["positive_months"]) + '/'
            + str(job["months_observed"]) + '</b> · Fees USD/oz: <b>'
            + f'{job["all_in_fees_usd_per_oz"]:,.2f}' + '</b></p>'
            '<p class="sub">Worst month: <b>' + _e(job["worst_month_utc"])
            + ' · ' + _money(job["worst_month_net_usd_per_oz"])
            + '</b> · Observed M1 floating DD: <b>' + risk + '</b></p>'
            '<p class="sub">Nonpositive-month streak: <b>'
            + str(job["longest_nonpositive_observed_month_streak"])
            + '</b> · Worst 3 complete months: <b>' + _money(worst_three)
            + '</b></p></article>'
        )
        for month in job["monthly"]:
            label = _e(month["month_utc"])
            dd = _money(month["max_observed_m1_global_peak_drawdown_usd_per_oz"])
            gaps = month["observed_m1_gap_events_from_prior_mark"]
            rows.append(
                '<tr data-verified-job="' + ident + '" data-verified-month="' + label
                + '"><th scope="row">' + ident + '</th><td>' + label
                + '</td><td class="number">' + _money(month["net_usd_per_oz"])
                + '</td><td class="number">' + str(month["trades"])
                + '</td><td class="number">' + f'{month["all_in_fees_usd_per_oz"]:,.2f}'
                + '</td><td class="number">' + str(month["observed_m1_samples"])
                + '</td><td class="number">' + dd + '</td><td class="number">'
                + (str(gaps) if gaps is not None else "N/A") + '</td></tr>'
            )
    options = "".join('<option value="' + _e(job["id"]) + '">'
                      + _e(job["id"]) + '</option>' for job in jobs)
    summary = (
        '<p class="sub">' + str(len(jobs)) + ' source-reconciled historical standalone jobs; '
        + str(report["not_executed_jobs"]) + ' not executed; '
        + str(report["hash_pinned_m1_jobs"]) + ' independently M1-pinned; '
        '0 prospective months · 0 approved strategies. '
        'No combined portfolio performance is asserted.</p>'
    )
    if not jobs:
        return summary + '<p class="sub">No source-verified executed jobs in this frozen batch.</p>'
    return (
        summary + '<div class="compare-grid">' + "".join(cards) + '</div>'
        '<div class="section-head"><h2 data-i18n="monthlyLedger">Verified UTC monthly ledger</h2>'
        '<div class="controls"><label for="verifiedJobFilter" data-i18n="monthlyJob">Job</label>'
        '<select id="verifiedJobFilter" aria-label="Filter verified job">'
        '<option value="">All verified jobs</option>' + options + '</select>'
        '<label for="verifiedMonthFilter" data-i18n="monthlyMonth">UTC month</label>'
        '<input id="verifiedMonthFilter" type="search" placeholder="YYYY-MM" '
        'aria-label="Filter verified UTC month"></div></div>'
        '<div id="verifiedMonthCount" class="subtle-line" role="status" aria-live="polite"></div>'
        '<div class="tablewrap"><table><caption>Source-reconciled historical exit-booked '
        'monthly P/L; NOT prospective OOS or executable portfolio returns</caption>'
        '<thead><tr><th scope="col">Job</th><th scope="col">UTC month</th>'
        '<th scope="col">Net USD/oz</th><th scope="col">Trades</th>'
        '<th scope="col">Fees USD/oz</th><th scope="col">M1 marks</th>'
        '<th scope="col">Observed floating DD</th><th scope="col">M1 gaps</th>'
        '</tr></thead><tbody id="verifiedMonthRows">' + "".join(rows)
        + '</tbody></table></div>'
        '<p class="sub">Frozen plan SHA256: <code>' + _e(report["plan_sha256"])
        + '</code>. M1 drawdown and gaps are N/A without independently '
        'pinned canonical equity evidence. No missing minutes fabricated.</p>'
    )
