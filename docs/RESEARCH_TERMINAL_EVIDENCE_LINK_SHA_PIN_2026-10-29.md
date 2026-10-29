# Quant Terminal — explicit SHA-targeted evidence links (2026-10-29)

The offline bilingual terminal previously linked every registry report to a moving GitHub branch. A future commit can change the linked content while a saved terminal still displays the earlier registry statistics. This is an auditability risk, **not** a market-result finding.

New opt-in: `python scripts/research_terminal.py --evidence-commit <exact-40-lowercase-hex-sha>`. The terminal will point report links at `/blob/<sha>/docs/...` or `/blob/<sha>/research/...` instead of the moving branch. The SHA is strictly syntax-checked; **existence, contents, relationship to the registry and current HEAD are not verified by this switch**. Operators must independently confirm that each report actually exists at the pinned commit and that the registry snapshot matches it. Without the flag, links retain prior behavior but are explicitly labeled **mutable branch; not SHA-pinned**. No network access is added.

Security tests reject malformed refs, HTML injection via refs, and accidental fallback to mutable links when SHA-targeted. Existing report path allowlist and HTML escaping remain in force. Synthetic UI tests only; no new original Gold ZIP replay, monthly P/L, floating M1 drawdown, shared-capacity portfolio, OOS or approved strategy.

No raw private BID/ASK data, live trading, broker access, billing, privacy or merge change. Keep PR #1 Draft. Full-head CI must pass before treating this increment as verified.
