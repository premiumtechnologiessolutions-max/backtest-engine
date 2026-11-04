# Global multiple-testing diagnostic — all strategy shards

This *mathematical construction module* accepts exact supplied p-value
fractions for the **complete, frozen strategy universe**. It rejects a
partial shortlist, duplicate identities (handled by sharding), invalid
fractions or unknown extra candidates.

Two correction methods are implemented:
- Bonferroni (familywise error under individually valid p-values).
- Benjamini–Yekutieli (step-up false-discovery rate control with arbitrary
  candidate dependence, assuming the input p-values are valid).

The global universe spans ALL shards; correction is NOT incorrectly reset
per shard. The procedure produces **nominal diagnostics only**. It cannot
prove p-value validity, market edge, prospective OOS, causal performance or
execution accuracy. No strategy is accepted or recommended by this module.
It does not yet hook into an independent acceptance engine, and the
sharded plan deliberately continues to report
`cross_shard_multiple_testing_control_implemented=False` until a complete
end-to-end evidence policy exists.

Location: `src/norisk_quant/global_multiplicity.py`
Regression: `tests/test_global_multiplicity.py`
Runs on synthetic fractions only, with no Gold data or broker access.
