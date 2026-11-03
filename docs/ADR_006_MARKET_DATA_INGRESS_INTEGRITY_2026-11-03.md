# ADR 006 — Source Integrity Is an Ingress Requirement

Status: accepted for research data ingress; NOT certified for broker fill execution.
Date: 2026-11-03. NoRiskFX multi-asset research; original Gold ZIP untouched.

## Decision

An original market quote is not trusted just because a provider API returns
HTTP 200 or a candle is marked "complete". M1 BID/ASK must satisfy:
(1) finite, strictly positive float-representable prices;
(2) each side's OHLC geometry;
(3) ASK open/high/low/close >= corresponding BID open/high/low/close;
(4) strictly increasing, UTC **minute-aligned** times;
(5) bounded size (<=5000 candles) and closed bars.
A missing timestamp is left missing, never forward-filled.
The online read-only practice request uses an integral M1 UTC interval.
There are no OANDA order/position/account endpoints in this adapter.

Non-crossing high/low is required because if ask(t)>=bid(t) for every
observed quote t, then max(ask)>=max(bid) and min(ask)>=min(bid).
An inverted aggregated extreme signals corrupt or mismatched source rows;
it must never be transformed into a fictitious arbitrage/spread advantage.

## Research related to platform completeness

- [Hypothesis](https://github.com/HypothesisWorks/hypothesis) (MPL-2.0):
  property/stateful model tests of retries, process crashes, rank/arbiter state.
  Not installed yet; avoid new dependencies until a bounded benchmark wins.
- [Open Policy Agent](https://github.com/open-policy-agent/opa) (Apache-2.0):
  policy-as-code and testable permissions. Use a *small local deterministic
  permission graph* first, no separate OPA host needed.
- [Gitleaks](https://github.com/gitleaks/gitleaks) (MIT) and
  [pip-audit](https://github.com/pypa/pip-audit) (Apache-2.0):
  future secrets and package vulnerability CI gates with false-positive
  handling and pinned runner versions; current workflows do not prove these.
- [OpenSSF Scorecard](https://github.com/ossf/scorecard) (Apache-2.0):
  upstream dependency governance; a good score is not proof of correct
  financial accounting or private data handling.
- [Litestream](https://github.com/benbjohnson/litestream) (Apache-2.0):
  single-host SQLite WAL disaster recovery, but only *after* defining
  transactional job/event state. Remote replication needs access/privacy
  policy and restore drill.
- [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python)
  (Apache-2.0): structured spans across experiment propose/freeze/run/audit.
  Never export broker credentials, raw quotes or unpublished holdout outcomes.
- [Schemathesis](https://github.com/schemathesis/schemathesis) (MIT):
  schema-driven HTTP API fuzzing once QuantLab's read-only API is frozen.
- [Pandera](https://github.com/unionai-oss/pandera) (MIT):
  column/row validations for source importer; source-side checks are needed
  even before conversion into a DataFrame.

This fix makes the existing OANDA BA candle adapter reject a few more
corrupt-input classes, with tests. It does not claim independent price feed
provenance, temporal macro fidelity, authenticated NFP dissemination or
M1-to-tick equivalence. It does not add a second trading executor, second
research supervisor, or new runtime library.

## Next blocking architecture gates

- **Single experiment lifecycle owner**: existing grid/director/console must
  share one append-only transactional event/job index. An LLM proposal is
  never an authorized code/market/reviewer mutation.
- **Evidence-origin gate**: the existing audited XAU trades/equity/monthly
  exporter remains canonical; select/mutate only after receipts from the
  actual ledger, not an arbitrary agent-supplied scalar fitness.
- **Bitemporal macro**: store release, first_seen, vintage, correction and
  source; evaluate timestamped adverse tests incl. rate decision revisions.
- **Multi-instrument accounting**: OANDA contract units, bid/ask sides,
  financing, account-currency conversion, market close, partial fills.
  XAU's historical 0.40 USD/oz all-in assumption is NEVER a universal FX fee.
- **Fault injection**: 24/7 deployment must survive queue duplicates, power
  loss, disk full, clock skew, unclean restart; verify exactly-once *ledger
  effect* via idempotent state transitions, not exactly-once network delivery.
- **Science**: preregistered future one-use holdout and familywise error
  control. No present candidate has independently verified OOS edge.

Release approval remains blocked until these are demonstrated on an actual
private host with original dataset and independently reconciled fills.
