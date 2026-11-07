# Quant Terminal — hash-pinned offline JavaScript CSP (2026-10-29)

## Integrity change

The premium bilingual read-only Quant Terminal previously embedded one interactive JavaScript controller without a Content Security Policy. This increment computes SHA256 over the **final exact UTF-8 script bytes**, and adds a meta CSP permitting only that controller. Additional or external script tags, empty script, or preexisting CSP metadata fail closed before export. Network connections, embedded frames, images, objects, workers, form submissions and base overrides are blocked; intentional GitHub evidence-link navigation is not disabled.

The terminal retains `style-src 'unsafe-inline'` because the bundled stylesheet and bounded inline progress-bar widths require inline CSS. This is **script hardening**, not a claim of a fully strict style CSP or complete browser isolation. The meta CSP applies when the browser honors meta-delivered directives; no server headers are set.

## Verification boundary

Nine local synthetic regressions passed before publication; one integration regression checks the actual premium terminal's controller hash and bilingual navigation markup in GitHub CI. Full GitHub CI on the exact resulting commit must be verified separately. No original Gold ZIP strategy backtest, new monthly P/L, floating drawdown, independent OOS or approved strategy is claimed (**N/A / 0**). Historical source and frozen $0.40/oz ALL-IN roundtrip rules are unchanged. PR #1 remains Draft; no live trading or private quote publication.
