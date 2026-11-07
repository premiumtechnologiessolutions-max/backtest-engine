# Durable static adapter design inbox (construction-only)

`scripts.durable_static_adapter_designs` stages inert field-name-only
adapter design manifests in two SQLite tables, independent of the executable
research jobs and attempts. No workers, vendor engines, market data, network,
or research execution are accessed.

- Entire batch validated before a write.
- One `BEGIN IMMEDIATE` transaction stages manifest and its request-ID index.
- Same content is idempotent; same request ID in another batch fails closed.
- Audit reconstructs manifest hashes, receipt binding, canonical JSON and
  complete request index, rejecting missing/extra/tampered rows.
- The API has **no** execution, job creation, research acceptance or external
  adapter import operation. `jobs_created=0` is a design invariant.
- This does not certify vendor execution, runtime sandboxing, OOS or actual
  trading results. Only synthetic unit tests are authorized at this stage.

Future integration needs a separately reviewed approval transition and a
real source attestation; this module intentionally does not provide one.
