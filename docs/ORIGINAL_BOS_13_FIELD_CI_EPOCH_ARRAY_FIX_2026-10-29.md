# Original BOS/H1 13-field parity: CI array conversion fix — 2026-10-29

## Verified failure and repair

GitHub Actions on commit `e02390ff663e1e9f21c5d8f52abb4e2a327800cd` failed **15** tests and passed **2,648** (one warning): `pd.to_numeric(saved, errors="raise")` returned a NumPy array because `saved` had already been converted via `observed.to_numpy()`. The subsequent `.to_numpy(dtype=np.int64)` raised `AttributeError` before any of the 13 archived-vs-current execution fields could be compared.

Commit `d229b900fb21c608ba0f97c7f2f44732ead701f9` converts the archived **pandas Series** directly to an `int64` array, then compares exact UTC epoch seconds. It leaves the frozen trading model, archive hashes, 13-field contract, tolerances and $0.40/oz ALL-IN cost unchanged.

**Exact-code GitHub Actions verification:** [run 40947077717](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40947077717) succeeded: **2,663 pytest passed, 1 warning**, including the previously failing 13-field synthetic parity cases. This verifies software tests only; it is **not** a new original-source strategy replay or clean out-of-sample result.

## Research and privacy boundaries

- Original-source strategy backtests added: **0**. New verified monthly P/L: **N/A**. New original-source M1 floating drawdown: **N/A**.
- Historical 2012–2019 source/archived-ledger matching reported in PR remains historically exposed and does not certify broker ticks or independent OOS.
- Private Gold ZIP and archived execution ledger are not committed; no live trading, billing, visibility or PR merge action.
- This report records the CI repair; it does not increase the factory's independent hypothesis count or promote any strategy.
