# Source-code provenance for frozen quantitative strategy designs

`norisk_quant.strategy_source_audit.audit_campaign_sources` checks the
real bytes of every strategy source and frozen spec referenced by a
sharded research campaign. Files must be local regular, bounded and
non-symlinked; paths are restricted to our source/docs/research directories.
A Python source is parsed by AST **without importing or executing it**.

Every candidate in the global family must be mapped; the check cannot
quietly inspect only winners. A source or spec SHA256 mismatch fails
closed and no market data are read. The returned manifest contains
relative paths, sizes and SHA256 identifiers only — no source text,
broker data, credentials, strategy results or metrics.

Important boundary: a local file hash does NOT prove trusted Git commit
ancestry, branch cleanliness, valid Gold archive content, fill accounting,
actual strategy execution or profitability. Those remain separate gates
requiring independent evidence.

Synthetic tests in `tests/test_strategy_source_audit.py` cover tampering,
unsafe paths, symlinks, incomplete universes and syntax errors.
No external projects or live market processes are run.
