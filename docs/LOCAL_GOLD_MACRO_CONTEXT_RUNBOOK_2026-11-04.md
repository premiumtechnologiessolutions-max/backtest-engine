# Running a read-only Gold + OpenBB causal context on local source

The command `python -m scripts.research_gold_macro_context` is now a
real offline research entrypoint, consuming the existing original annual
Gold ZIP loader (not a synthetic engine) and optional locally captured
OpenBB/FRED snapshot. It does **not** fetch remote data itself, trade,
backtest strategies, or verify independent 13-field trade replay.

```bash
python -m scripts.research_gold_macro_context \
  --gold-zip "/private/Gold data.zip" \
  --source-sha256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121 \
  --start 2024-01-03 --end 2024-01-03 \
  --decision-at 2024-01-03T15:00:00Z
```

Optional `--fred-snapshot /private/frozen_fred.json` uses a locally
captured JSON envelope produced by `freeze_fred_snapshot()`. The full
source ZIP must match the declared original SHA256 before parsing quotes.
Full M1 BID/ASK bars are only known after close; market source timestamps
remain original candle opens. Batches are capped to 50,000 M1 rows.

An OpenBB observation whose period date is in 2024 but whose snapshot was
captured in 2026 is invisible to a decision taken in 2024. Snapshot capture
time is **not** independently verified publication or vintage evidence.
This command prints only a small JSON summary, not raw quote rows or API
tokens, and does not publish anything to GitHub. Synthetic ZIP fixture
tests are included. It remains **offline read-only**, with no certified
strategy, OOS, original-data replay or broker fill result.
