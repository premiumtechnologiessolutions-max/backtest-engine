# No Risk FX — localhost research monitor Host and clock integrity (2026-10-30)

## Risk found during independent operational audit

A process bound to `127.0.0.1` is **not by itself** a complete
DNS-rebinding defense. Before this patch, `scripts/research_local_monitor.py`
accepted any HTTP `Host` header, including a hostname that a remote
website might resolve to loopback. Browser private-network protections
are variable and must not be the only defense for local research metadata.

The monitor also clamped all future-dated `campaign_status.json`
timestamps to zero seconds old. A mistakenly future-dated snapshot could
appear fresh instead of failing closed.

## Changes and explicit contracts

1. Before any read of campaign state or verified generation evidence,
   require **exactly one** HTTP Host header matching
   `127.0.0.1:<actual listening port>`. Missing, duplicate, malicious,
   alternate-hostname and portless Host headers return **403**. The
   monitor's own printed URL remains the canonical browser address.
   The server continues to bind only to IPv4 loopback and to serve only
   its three GET endpoints. This is a local-read safety gate, not
   authentication or permission for internet exposure.
2. Require a timezone-aware, zero-offset UTC campaign update timestamp.
   Reject observations more than **60 seconds ahead** of the trusted
   local monitor clock. A future offset of at most 60 seconds is treated
   as age zero to tolerate small clock skew. Reject a naive monitor
   clock passed by test/integration callers.
3. Add real loopback HTTP regression cases for the valid Host, missing
   Host, hostile DNS name, `localhost` alias, missing port and duplicate
   Host on all three allowlisted endpoints. Assert forbidden responses
   contain neither campaign JSON nor the research HTML. Add controlled
   UTC clock-skew tests.

## Verification boundaries

The changes are covered by synthetic/local HTTP regression tests in
`tests/test_research_local_monitor.py`; whole-repository CI must be
checked against the **exact post-change commit**, not inferred from a
previous green run. This audit does **not** run the original Gold ZIP,
advance an independent OOS sample, measure strategy P/L, authorize
broker trading, make the UI remote-accessible, or validate 24/7 hosting.

The repository is currently **PUBLIC** per GitHub metadata. No private
original Gold ZIP, market quotes, individual trade ledger, account
credentials or research campaign evidence was uploaded. Keep Draft PR #1
unmerged until the remaining release and independent validation gates.
