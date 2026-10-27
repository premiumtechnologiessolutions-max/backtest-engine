"""Premium, offline, read-only presentation of audited NRFX research metadata.

Input is exclusively dashboard_model output from research_terminal.py. This
module has no data fetching, trading interfaces, or inferred P/L curves.
"""
from __future__ import annotations

from html import escape
from urllib.parse import quote

REPO = "https://github.com/premiumtechnologiessolutions-max/backtest-engine/blob/feat/quant-engine-foundation/"


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _n(value: int) -> str:
    if type(value) is not int or value < 0:
        raise ValueError("Display totals must be nonnegative integers")
    return format(value, ",")


def render_premium_html(model: dict) -> str:
    """Build a self-contained, responsive research terminal. Does not certify returns."""
    rows = model["rows"]
    for row in rows:
        if type(row["best_positive_months"]) is not int or not 0 <= row["best_positive_months"] <= 24:
            raise ValueError("Best positive months must be within 0..24")
    best = sorted(rows, key=lambda r: (-r["best_positive_months"], r["id"]))[:6]
    ranks = []
    for row in best:
        pct = row["best_positive_months"] * 100 / 24
        ranks.append(
            '<div class="bar-row"><span class="bar-label">' + _e(row["id"]) + '</span>'
            + '<div class="bar-track"><div class="bar-fill" style="width:' + str(round(pct, 2)) + '%"></div></div>'
            + '<span class="bar-val">' + str(row["best_positive_months"]) + '/24</span></div>'
        )
    row_html = []
    for row in rows:
        report = row.get("report")
        if report is not None:
            from pathlib import PurePosixPath
            import re
            if (type(report) is not str or not re.fullmatch(r"(?:docs|research)/[A-Za-z0-9._/-]+", report)
                    or ".." in PurePosixPath(report).parts):
                raise ValueError("Unsafe evidence path")
        link = ('<a href="' + _e(REPO + quote(report, safe="/"))
                + '" target="_blank" rel="noopener noreferrer">Read evidence</a>') if report else '<span class="quiet">Not linked</span>'
        status = row["status"]
        if any(term in status.upper() for term in ("REJECT", "FAIL")):
            color = "rejected"
        elif "ZERO" in status.upper() or "CONTROL" in status.upper():
            color = "neutral"
        else:
            color = "unverified"
        row_html.append('''<tr data-search="''' + _e(" ".join([row["id"], row["family"], status]).lower()) + '''"
 data-status="''' + color + '''" data-months="''' + str(row["best_positive_months"]) + '''"
 data-specs="''' + str(row["specs"]) + '''">
<td><label class="check-cell"><input class="compare-check" type="checkbox" aria-label="Compare ''' + _e(row["id"]) + '''"><b>''' + _e(row["id"]) + '''</b></label></td>
<td class="family">''' + _e(row["family"]) + '''</td>
<td class="number">''' + _n(row["specs"]) + '''</td>
<td class="number">''' + _n(row["active_replays"]) + '''</td>
<td><div class="months"><progress max="24" value="''' + str(row["best_positive_months"]) + '''">''' + str(row["best_positive_months"]) + ''' / 24</progress><span>''' + str(row["best_positive_months"]) + ''' / 24</span></div></td>
<td><span class="pill ''' + color + '''">''' + _e(status) + '''</span></td>
<td>''' + link + '''</td></tr>''')
    metric_defs = [
        ("PARAMETER SPECS", "specifications", "Correlated configurations"),
        ("ANNUAL REPLAYS", "annual_replays", "Runs with filled trades"),
        ("RESEARCH FAMILIES", "families", "Distinct hypotheses in registry"),
        ("24/24 PASS", "passing_24_of_24", "Historical design gate only"),
    ]
    cards = "".join(
        '<article class="metric"><div class="metric-label">' + label + '</div><div class="metric-value">'
        + _n(model[key]) + '</div><div class="metric-hint">' + detail + '</div></article>'
        for label, key, detail in metric_defs
    )
    html = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="referrer" content="no-referrer">
<title>NO RISK FX | Quant Research Terminal</title>
<style>
:root{color-scheme:dark;--bg:#070e1b;--surface:#101b2d;--surface2:#162339;--line:#26384d;--muted:#8b9bb4;--copy:#e8eef7;--gold:#e2bb73;--blue:#7bb5ff;--green:#9acdb8;--orange:#f2ad82;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--copy)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse 850px 500px at 55% -170px,#19325099,transparent),var(--bg);min-height:100vh}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--gold);outline-offset:3px}a{color:#acd4ff;text-decoration:none}a:hover{text-decoration:underline}.app{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}.sidebar{border-right:1px solid var(--line);background:#0a1423e8;padding:28px 20px;display:flex;flex-direction:column;gap:30px}.brand{display:flex;gap:11px;align-items:center}.emblem{width:42px;height:42px;display:grid;place-items:center;border:1px solid #bfa56a88;border-radius:12px;background:linear-gradient(135deg,#223d5b,#0b1727);color:var(--gold);font-size:23px;font-weight:800}.brand strong{display:block;font-size:15px;letter-spacing:.11em}.brand span{display:block;color:var(--gold);font-size:10px;letter-spacing:.19em;margin-top:3px}.nav-list{display:grid;gap:8px}.nav-caption,.eyebrow{font-size:11px;letter-spacing:.19em;color:#8ca2bb;font-weight:700;text-transform:uppercase}.nav-button{border:1px solid transparent;background:transparent;padding:13px 14px;border-radius:10px;text-align:left;color:#b3c1d3;display:flex;align-items:center;gap:12px}.nav-button:hover,.nav-button.active{background:#182d45;color:#fff;border-color:#294661}.nav-icon{font-size:18px;width:20px;text-align:center;color:var(--gold)}.sidebar-note{margin-top:auto;border:1px solid #35445a;background:#101e30;padding:15px;border-radius:12px;font-size:12px;line-height:1.6;color:#b1c3d8}.sidebar-note b{color:var(--gold)}.main{padding:30px clamp(18px,3vw,50px) 60px;min-width:0;max-width:1700px;width:100%;margin:0 auto}.top{display:flex;justify-content:space-between;gap:16px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:22px}.status-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;color:#d2dce9;font-size:12px}.dot{width:7px;height:7px;background:#c99c54;border-radius:50%;box-shadow:0 0 0 4px #c99c5425}.date{color:var(--muted);font-size:12px}.hero{display:flex;gap:25px;align-items:flex-end;justify-content:space-between;padding:34px 0 24px}.hero h1{font-size:clamp(30px,3.8vw,56px);letter-spacing:-.045em;line-height:1.06;margin:10px 0 12px;font-weight:760}.hero p{max-width:670px;color:#acbfd3;line-height:1.7;margin:0;font-size:14px}.accent{color:var(--gold)}.hero-mark{font-size:11px;text-transform:uppercase;color:var(--gold);letter-spacing:.15em;border:1px solid #a08b624a;padding:10px 14px;border-radius:99px;white-space:nowrap}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric,.panel{background:linear-gradient(145deg,#122239,#0d1a2b);border:1px solid var(--line);border-radius:16px}.metric{padding:20px 21px;min-height:143px}.metric-label{color:#a7bdd3;font-size:11px;letter-spacing:.12em}.metric-value{font-size:clamp(24px,2.3vw,37px);font-weight:770;letter-spacing:-.04em;margin:14px 0 9px;font-variant-numeric:tabular-nums}.metric-hint{font-size:11px;color:var(--muted)}.metric:last-child .metric-value{color:var(--gold)}.grid-two{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(250px,.9fr);gap:15px;margin:16px 0}.panel{padding:23px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.panel h2{font-size:17px;margin:0}.sub{color:#98abc1;font-size:12px;line-height:1.55;margin:8px 0 18px}.tag{font-size:10px;color:#e4c796;border:1px solid #94744666;border-radius:99px;padding:6px 9px}.bar-list{display:grid;gap:15px}.bar-row{display:grid;grid-template-columns:110px minmax(0,1fr) 46px;align-items:center;gap:12px;font-size:12px}.bar-label{color:#cfdbeb;white-space:nowrap}.bar-track{height:9px;border-radius:10px;background:#243954;overflow:hidden}.bar-fill{height:100%;border-radius:10px;background:linear-gradient(90deg,#557aaa,#e0ba74)}.bar-val{color:#e4c990;font-variant-numeric:tabular-nums;text-align:right}.checkpoint{display:flex;gap:13px;padding:13px 0;border-bottom:1px solid #23374b}.checkpoint:last-child{border:0}.step{width:30px;height:30px;flex-shrink:0;display:grid;place-items:center;border:1px solid #486079;border-radius:9px;color:var(--gold);font-weight:700}.checkpoint b{display:block;font-size:13px}.checkpoint span{display:block;font-size:11px;line-height:1.5;color:#99acc2;margin-top:4px}.warning{border:1px solid #7d684b;background:#231f1b9c;padding:15px 18px;border-radius:13px;color:#e4d7be;line-height:1.6;font-size:12px;margin:16px 0}.warning b{color:#f1cb88}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:24px 0 14px}.section-head h2{font-size:21px;margin:0 0 5px}.section-head p{font-size:12px;color:var(--muted);margin:0}.controls{display:flex;flex-wrap:wrap;gap:10px}.controls input,.controls select{padding:11px 13px;background:#111e30;color:#dce7f4;border:1px solid #35495e;border-radius:9px;min-width:160px}.controls input{min-width:min(260px,100%)}.tablewrap{border:1px solid var(--line);border-radius:13px;overflow:auto;background:#0d1a2a}table{border-collapse:collapse;width:100%;min-width:1040px}thead{background:#15253a}th{text-align:left;color:#9fb4c9;font-size:10px;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}td,th{padding:15px 13px;border-bottom:1px solid #26374c}td{font-size:12px;vertical-align:middle;color:#c8d5e5}tbody tr:hover{background:#18283c}tbody tr:last-child td{border-bottom:0}.check-cell{display:flex;gap:9px;align-items:center;white-space:nowrap}.check-cell input{accent-color:#d4af69;width:16px;height:16px}.family{min-width:250px;max-width:460px;line-height:1.45;color:#e5edf7}.number{font-variant-numeric:tabular-nums;white-space:nowrap}.months{display:flex;gap:9px;align-items:center;white-space:nowrap}.months progress{width:78px;height:8px;accent-color:#d7b373}.months span{color:#d9bb80;font-size:11px}.pill{display:inline-block;border-radius:6px;padding:7px 9px;max-width:240px;overflow-wrap:anywhere;font-size:10px;font-weight:700;letter-spacing:.015em;line-height:1.35}.rejected{color:#efbba4;background:#5c302c55}.unverified{color:#e6c896;background:#634f2852}.neutral{color:#b8c6d7;background:#35425466}.quiet{color:var(--muted)}.compare-panel{margin-top:17px}.selection{display:flex;flex-wrap:wrap;gap:10px;align-items:center;min-height:45px}.selection .chip{font-size:12px;border:1px solid #7b693f;border-radius:999px;color:#e8d09d;padding:7px 12px;background:#2c2b24}.compare-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.compare-card{padding:14px;border:1px solid #35445a;border-radius:10px;background:#112035}.compare-card b{display:block;margin-bottom:8px}.compare-card div{font-size:12px;color:#abc0d7;line-height:1.7}.message{color:#a4b6cb;font-size:12px;line-height:1.6}.view[hidden]{display:none!important}.method-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.method-grid h3{margin:0 0 7px;color:var(--gold);font-size:15px}.method-grid p{font-size:13px;line-height:1.7;color:#b1c3d6;margin:0}.footer{border-top:1px solid var(--line);margin-top:27px;padding-top:20px;display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;font-size:11px;color:#869bb3}#count{font-size:12px;color:#97adc3}html[dir=rtl] .main,html[dir=rtl] .sidebar{direction:rtl}html[dir=rtl] .sidebar{border-right:0;border-left:1px solid var(--line)}html[dir=rtl] th{text-align:right}html[dir=rtl] .bar-val{text-align:left}html[dir=rtl] .nav-button{text-align:right}html[dir=rtl] .bar-row{direction:rtl}button.ghost{background:#1a3048;border:1px solid #49617a;color:#d5e7f5;border-radius:9px;padding:10px 12px}.subtle-line{color:#7d95aa;font-size:11px;margin-top:10px}
@media(max-width:1150px){.app{grid-template-columns:75px minmax(0,1fr)}.sidebar{padding:22px 11px}.brand>div:last-child,.nav-button .nav-text,.nav-caption,.sidebar-note{display:none}.nav-button{justify-content:center}.brand{justify-content:center}.grid-two{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.app{display:block}.sidebar{padding:12px 14px;display:flex;flex-direction:row;align-items:center;gap:14px;border-right:0;border-bottom:1px solid var(--line)}.brand>div:last-child{display:block}.nav-list{display:flex;gap:3px;margin-left:auto}.nav-button{padding:9px}.nav-caption{display:none}.sidebar-note{display:none}.main{padding:16px 14px 38px}.top{align-items:flex-start}.hero{display:block;padding:26px 0 18px}.hero-mark{display:inline-block;margin-top:16px}.stats{gap:9px}.metric{padding:14px;min-height:120px}.metric-value{font-size:25px}.metric-label{font-size:9px}.metric-hint{font-size:10px}.panel{padding:17px}.bar-row{grid-template-columns:88px minmax(0,1fr) 38px;gap:6px}.controls,.controls input,.controls select{width:100%}.method-grid,.compare-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:no-preference){button,.nav-button,.metric{transition:background .18s ease, border-color .18s ease}.metric:hover{border-color:#527096}}
</style></head><body>
<div class="app"><aside class="sidebar"><div class="brand"><div class="emblem" aria-hidden="true">✧</div><div><strong>NO RISK FX</strong><span>QUANT RESEARCH</span></div></div><nav class="nav-list" aria-label="Main sections"><span class="nav-caption">WORKSPACE</span><button type="button" class="nav-button active" data-view="overview" aria-current="page"><span class="nav-icon">◈</span><span class="nav-text" data-i18n="overview">Overview</span></button><button type="button" class="nav-button" data-view="catalog"><span class="nav-icon">▤</span><span class="nav-text" data-i18n="strategyLab">Strategy Lab</span></button><button type="button" class="nav-button" data-view="method"><span class="nav-icon">◇</span><span class="nav-text" data-i18n="verification">Verification</span></button></nav><div class="sidebar-note"><b>RESEARCH ENVIRONMENT</b><br>Offline metadata viewer only.<br>No orders, broker keys, live accounts or API access.</div></aside>
<main class="main"><div class="top"><div class="eyebrow">INSTITUTIONAL RESEARCH DESK <span class="accent">/ XAUUSD</span></div><div class="status-top"><span class="dot" aria-hidden="true"></span><span data-i18n="readOnly">READ ONLY · HISTORICAL</span><button type="button" id="languageToggle" class="ghost" lang="ar" aria-label="Switch to Arabic" aria-pressed="false">العربية</button></div></div>
<section class="view" id="overview"><div class="hero"><div><div class="eyebrow">RESEARCH INTELLIGENCE</div><h1><span data-i18n="quantResearch">Quant Research</span><br><span class="accent" data-i18n="commandCenter">Command Center.</span></h1><p>Track systematic hypotheses, evaluate historical research coverage and examine evidence—without confusing backtest statistics with verified future returns.</p></div><div class="hero-mark">v1.1 / VERIFIED COUNTS ONLY</div></div><div class="stats">__CARDS__</div>
<div class="grid-two"><article class="panel"><div class="panel-head"><div><h2 data-i18n="coverage">Historical design-month coverage</h2><p class="sub">Maximum positive months achieved by a parameter specification in each family (2012–2013 exposed design). Not an equity curve or forward result.</p></div><span class="tag">TOP 6 · EXPOSED</span></div><div class="bar-list">__RANKS__</div></article><article class="panel"><div class="panel-head"><div><h2 data-i18n="pathway">Validation pathway</h2><p class="sub">Research gates and what the metadata can verify.</p></div></div><div class="checkpoint"><div class="step">01</div><div><b>Registry integrity</b><span>Arithmetic checked before the page is generated.</span></div></div><div class="checkpoint"><div class="step">02</div><div><b>Execution fidelity</b><span>Inspect each experiment report; no automatic broker-fill certification.</span></div></div><div class="checkpoint"><div class="step">03</div><div><b>Independent prospective OOS</b><span>Not established by this historical registry. Do not promote to live.</span></div></div></article></div>
<div class="warning"><b>Important:</b> Correlated parameters are not independently proven strategies. Historical design years 2012–2013 have been exposed during research. Passing a historical monthly gate cannot promise next month's profit; this dashboard makes no profitability claim. Static metadata audit is not broker-tick, independent OOS or live-trading validation.</div>
<button class="ghost" type="button" data-goto="catalog" data-i18n="exploreFamilies">Explore research families →</button></section>
<section class="view" id="catalog" hidden><div class="hero"><div><div class="eyebrow">STRATEGY RESEARCH</div><h1><span data-i18n="explore">Explore the</span> <span class="accent" data-i18n="factory">factory.</span></h1><p>Every family is a frozen research hypothesis. Search, order and compare its documented design-month coverage.</p></div><div class="hero-mark">METADATA / NO TRADING</div></div>
<div class="section-head"><div><h2 data-i18n="catalogue">Experiment catalogue</h2><p>Performance values here are historical design metrics, not verified expected returns.</p></div><div class="controls"><input type="search" id="filter" placeholder="Search name, ID or status" aria-label="Search experiment catalogue"><select id="statusFilter" aria-label="Filter by research status"><option value="all">All statuses</option><option value="rejected">Rejected</option><option value="unverified">Other / unverified</option><option value="neutral">No-trade / control</option></select><select id="sort" aria-label="Sort research families"><option value="months">Best positive months</option><option value="specs">Most parameter specs</option><option value="id">Experiment ID</option></select></div></div>
<div class="tablewrap"><table><thead><tr><th>Compare / ID</th><th>Hypothesis</th><th>Specs</th><th>Annual replays</th><th>Best months</th><th>Reported state</th><th>Evidence</th></tr></thead><tbody id="experimentRows">__ROWS__</tbody></table></div><div class="subtle-line" id="count" role="status" aria-live="polite"></div>
<article class="panel compare-panel"><div class="panel-head"><div><h2 data-i18n="comparison">Research comparison</h2><p class="sub">Select up to three families. Comparison is descriptive, not a strategy recommendation.</p></div><button type="button" class="ghost" id="clearCompare" data-i18n="clear">Clear</button></div><div id="selection" class="selection" aria-live="polite"><span class="message">Select families above to compare audited metadata.</span></div><div id="compareGrid" class="compare-grid"></div></article></section>
<section class="view" id="method" hidden><div class="hero"><div><div class="eyebrow">EVIDENCE & VALIDATION</div><h1><span data-i18n="trust">Trust the</span> <span class="accent" data-i18n="process">process.</span></h1><p>Clear boundaries around what the engine has measured—and what remains unproven.</p></div><div class="hero-mark">NO OOS CERTIFICATE</div></div><div class="method-grid"><div class="panel"><h3 data-i18n="provenance">Data provenance</h3><p>Factory counts are derived from its published registry, which is arithmetically audited. This page does not fetch or expose the raw gold archive.</p></div><div class="panel"><h3 data-i18n="assumptions">Backtesting assumptions</h3><p>Research fixed-cost scenario: $__FEE__ per ounce, all-in round trip. Actual broker spread, ticks, fill sequence and slippage need separate verification.</p></div><div class="panel"><h3 data-i18n="designOos">Design vs. independent OOS</h3><p>Previously examined 2012–2013 results can support method development only. A prospective holdout, frozen rules and robust performance gates are required before advancing a candidate.</p></div><div class="panel"><h3 data-i18n="availability">Performance availability</h3><p>Weekly/monthly P&amp;L, win rates and equity curves are <b>N/A in this dashboard</b> until run-level verified files are attached. No illustrative curve is shown as real performance.</p></div></div><div class="warning"><b>Registry status:</b> __STATUS__<br><b>Last updated:</b> __UPDATED__ (source-provided UTC)</div></section>
<footer class="footer"><span>NO RISK FX © 2026 · QUANT RESEARCH</span><span>Offline read-only HTML · No external scripts, analytics or broker access</span><span>Registry: __UPDATED__</span></footer></main></div>
<script>
(function(){'use strict';
const nav=[...document.querySelectorAll('[data-view]')],views=[...document.querySelectorAll('.view')];
function switchView(id){if(!views.some(v=>v.id===id))return;for(const v of views)v.hidden=v.id!==id;for(const b of nav){const active=b.dataset.view===id;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}window.scrollTo(0,0);}
for(const b of nav)b.addEventListener('click',()=>switchView(b.dataset.view));
for(const b of document.querySelectorAll('[data-goto]'))b.addEventListener('click',()=>switchView(b.dataset.goto));
const body=document.getElementById('experimentRows'),rows=[...body.querySelectorAll('tr')],search=document.getElementById('filter'),filter=document.getElementById('statusFilter'),sort=document.getElementById('sort'),count=document.getElementById('count');
function refresh(){const q=search.value.trim().toLocaleLowerCase(),status=filter.value;let shown=0;for(const row of rows){const ok=(!q||row.dataset.search.includes(q))&&(status==='all'||row.dataset.status===status);row.hidden=!ok;if(ok)shown++;}let ordered=rows.slice();if(sort.value==='months')ordered.sort((a,b)=>Number(b.dataset.months)-Number(a.dataset.months)||a.cells[0].textContent.localeCompare(b.cells[0].textContent));else if(sort.value==='specs')ordered.sort((a,b)=>Number(b.dataset.specs)-Number(a.dataset.specs));else ordered.sort((a,b)=>a.cells[0].textContent.localeCompare(b.cells[0].textContent));for(const row of ordered)body.appendChild(row);count.textContent=document.documentElement.lang==='ar'?(shown+' من '+rows.length+' عائلة بحثية معروضة'):(shown+' of '+rows.length+' research families shown');}
for(const e of [search,filter,sort])e.addEventListener(e===search?'input':'change',refresh);refresh();
const selection=document.getElementById('selection'),grid=document.getElementById('compareGrid'),clear=document.getElementById('clearCompare');
const fmt=n=>Number(n).toLocaleString('en-US');
function updateCompare(){const chosen=rows.filter(r=>r.querySelector('.compare-check').checked);selection.replaceChildren();grid.replaceChildren();if(!chosen.length){const s=document.createElement('span');s.className='message';s.textContent=document.documentElement.lang==='ar'?'اختر عائلات بحثية للمقارنة بين البيانات المدقّقة.':'Select families above to compare audited metadata.';selection.appendChild(s);return;}for(const row of chosen){const chip=document.createElement('span');chip.className='chip';chip.textContent=row.cells[0].textContent.trim();selection.appendChild(chip);const card=document.createElement('div');card.className='compare-card';const head=document.createElement('b');head.textContent=row.cells[0].textContent.trim();const content=document.createElement('div');content.textContent=document.documentElement.lang==='ar'?(row.cells[1].textContent.trim()+' | المعاملات: '+row.cells[2].textContent.trim()+' | الاختبارات السنوية: '+row.cells[3].textContent.trim()+' | أفضل أشهر: '+row.dataset.months+'/24 | الحالة: '+row.cells[5].textContent.trim()+' | أسوأ شهر: N/A | السحب العائم: N/A | الربح الشهري: N/A'):(row.cells[1].textContent.trim()+' | Specs: '+row.cells[2].textContent.trim()+' | Annual replays: '+row.cells[3].textContent.trim()+' | Best months: '+row.dataset.months+'/24 | State: '+row.cells[5].textContent.trim()+' | Worst month: N/A | Floating DD: N/A | Monthly P/L: N/A');card.append(head,content);grid.appendChild(card);}}
for(const row of rows){const check=row.querySelector('.compare-check');check.addEventListener('change',()=>{if(check.checked&&rows.filter(r=>r.querySelector('.compare-check').checked).length>3){check.checked=false;count.textContent=document.documentElement.lang==='ar'?'الحد الأقصى 3 عائلات للمقارنة.':'Maximum 3 families for comparison.';}updateCompare();});}
clear.addEventListener('click',()=>{for(const r of rows)r.querySelector('.compare-check').checked=false;updateCompare();});
const languageToggle=document.getElementById('languageToggle');
const englishLabels=Object.fromEntries([...document.querySelectorAll('[data-i18n]')].map(el=>[el.dataset.i18n,el.textContent]));
const arabicLabels={
 overview:'نظرة عامة',strategyLab:'مختبر الاستراتيجيات',verification:'التحقّق',
 readOnly:'للقراءة فقط · نتائج تاريخية',quantResearch:'البحث الكمي',commandCenter:'مركز التحكّم',
 explore:'استكشف',factory:'عائلات البحث',trust:'ثق في',process:'منهجية التحقّق',
 coverage:'تغطية الأشهر التاريخية للتصميم',pathway:'مراحل التحقّق',
 catalogue:'سجلّ التجارب',comparison:'مقارنة الأبحاث',
 provenance:'مصدر البيانات',assumptions:'افتراضات الاختبار',
 designOos:'التصميم مقابل الاختبار المستقبلي المستقل',availability:'توفر بيانات الأداء',
 clear:'مسح الاختيار',exploreFamilies:'استكشف عائلات البحث ←'
};
function setLanguage(ar){
 document.documentElement.lang=ar?'ar':'en';
 document.documentElement.dir=ar?'rtl':'ltr';
 languageToggle.textContent=ar?'English':'العربية';
 languageToggle.lang=ar?'en':'ar';
 languageToggle.setAttribute('aria-label',ar?'Switch to English':'Switch to Arabic');
 languageToggle.setAttribute('aria-pressed',String(ar));
 for(const el of document.querySelectorAll('[data-i18n]')){
   const key=el.dataset.i18n;
   el.textContent=ar?arabicLabels[key]:englishLabels[key];
 }
 refresh();updateCompare();
}
languageToggle.addEventListener('click',()=>setLanguage(document.documentElement.lang!=='ar'));
})();
</script></body></html>'''
    return (html.replace("__CARDS__", cards)
            .replace("__RANKS__", "".join(ranks) if ranks else '<p class="sub">No active families in audited registry.</p>')
            .replace("__ROWS__", "\n".join(row_html))
            .replace("__UPDATED__", _e(model["updated_utc"]))
            .replace("__STATUS__", _e(model["research_status"]))
            .replace("__FEE__", _e(format(float(model["fee"]), ".2f"))))