# Source-open exit entry provenance gate — 2026-10-29

## Scope
The independent `verify_source_open_exit_prices` audit now requires **both** `entry_at` and `closed_at` to be observed timestamps in the original, sorted, unique UTC M1 BID index. Previously it checked only `closed_at`, allowing a ledger whose recorded entry timestamp was not present in the original quote sample to pass this narrow audit. The opening-stop fill price must still equal the actual source M1 BID open and respect the adverse protective stop.

Additional fail-closed validation rejects duplicate trade-ledger columns and nonpositive protective stops. This applies to `open_stop`, `gap_stop`, and `entry_open_beyond_stop`. The original gap-versus-contiguous M1 classification and same-bar entry-open-stop rule remain unchanged.

## Regression evidence
Four tests added to `tests/test_source_exit_integrity.py`:
1. Invented off-grid entry timestamp for a previously opened position.
2. Invented same-bar entry/exit timestamp for an entry-open-beyond-stop.
3. Duplicate trade-ledger columns.
4. Nonpositive stop.

On 2026-10-29, **18/18 tests passed locally** on an isolated reconstruction of the source-open module and its test file (Python 3, pandas 2.2.3, pytest 9.0.2). This is **not** a claim that full repository pytest or GitHub Actions passed on the current branch. No workflow run was reported for the test commit at verification time.

## Research limitations
- No private raw `Gold data.zip` was uploaded or used.
- The canonical $0.40/oz all-in fee and strategy parameters are unchanged.
- No original-ZIP 13-field replay on this commit, no real-tick/broker-fill certification, and no fresh OOS research were performed.
- Historical BOS/H1 results remain rejected; do not interpret an audit pass as evidence of profitability.
- PR #1 must remain Draft until full pytest, independent original-source replay, and relevant CI verification succeed.
