# Arithmetic research cycle orchestrator — 2026-10-30

## Purpose

`scripts/run_arithmetic_research_cycles.py` joins the existing audited
research stages into one bounded synchronous command:

1. Verify the **original local private** Gold ZIP against the preregistered
   SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
2. Reproduce a deterministic frozen training-only arithmetic generation.
3. Materialize the immutable dispatch and formula index.
4. Run every formula/year in bounded, independently published shards using
   the canonical CLI with **both reference and fast execution**, fixed
   **$0.40 USD/oz ALL-IN** cost, and one-ounce size.
5. Compile the **entire** generation's feedback only after all original
   engine reports, monthly/weekly trade booking, BID/ASK fingerprints and M1
   observed-equity evidence pass the existing independent verifier.
6. Feed the next immutable training input into the next generation.

The public GitHub repository contains only code, docs and synthetic tests.
Never upload raw quotes, the original ZIP, real trade ledgers or private
training outputs. The GitHub PR remains Draft.

## Reproducible local invocation (authorized environment with source only)

```bash
python -m scripts.run_arithmetic_research_cycles \
  --training-input /private/frozen_training_input.json \
  --gold-zip "/private/Gold data.zip" \
  --out /private/nrfx_generations \
  --seed 19 --first-generation 1 --generations 2 \
  --count 8 --shard-size 2
```

The paths are illustrative; no claim is made that this command has executed
on the original Gold ZIP at this commit. This design deliberately exposes
no holdout-year parameter. Every selected year is read from the frozen
training input, revalidated against the underlying generator and dispatch.
All reports remain marked **TRAINING ONLY**, **NOT OOS**, **NO LIVE TRADING**.

### Resume and failure behavior

- A complete shard with the expected immutable index is reused after
  interruption; a different year/ordinal window, incomplete shard, symlinked
  output or invalid index fails closed. All reused reports receive a deep
  independent re-audit in the final feedback stage.
- A feedback input is not published if even one formula/year is missing or
  if any canonical parity/accounting/fingerprint audit fails.
- Existing immutable generations, dispatches and feedback inputs cannot
  silently be replaced; the canonical stage writers enforce identical-byte
  resumes or rejection.
- Bounded controls: **1–10 generations per invocation**, **1–128 formulas
  per generation**, **1–128 formulas per replay shard**. The current evolution
  engine also enforces a total training candidate pool cap of 128, so
  repeated generations can deliberately stop with a fail-closed capacity
  error. This is NOT an unlimited search service.
- Running a very large job takes wall-clock time and must have a permitted
  authorized compute environment. This script is synchronous; it is not a
  daemon, not a remote GitHub-runner trigger and not a persistent automation.

## Verification status

The orchestrator's control-flow implementation passed nine separately
constructed synthetic local tests before publication. GitHub
`tests/test_run_arithmetic_research_cycles.py` covers sequential
generations, complete annual sharding, idempotent replay skipping,
malformed resume records, integer bounds, SHA mismatch and symlink safety.

**Not yet verified by this new runner:** successful full GitHub CI on the
exact current HEAD, original-ZIP annual source replay, broker tick parity,
independent untouched prospective OOS, or live execution.

All previous negative BOS/H1 and quote-reopen gap strategies remain
rejected. No profitable strategy or monthly-return guarantee is implied.

## Exclusive private research-root writer gate

The orchestration entry point now acquires a **nonblocking POSIX advisory
flock** on `.nrfx_research.lock` before generation, dispatch, replay or
feedback. A concurrent process targeting the same output root fails closed
rather than racing immutable shard creation. The lock is a private (0600),
single-link regular file opened with `O_NOFOLLOW`; symlinked, nonregular or
world-readable lock files are rejected. Kernel locks are released on normal
return, Python exceptions and process termination. The lock inode is never
unlinked, avoiding the split-lock race. It is not a cross-machine/distributed
lock and does not serialize independent output roots.

Five synthetic regression tests cover an active writer, crash-like exception
release/resume, symlink, nonregular file and insecure permissions. No private
Gold source replay, monthly P/L, drawdown, or independent OOS is established
by these concurrency tests. This implementation requires a POSIX platform
(Linux GitHub Actions and local Linux runner).
