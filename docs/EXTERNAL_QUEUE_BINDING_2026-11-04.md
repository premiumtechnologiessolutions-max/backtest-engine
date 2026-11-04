# Immutable queue → external engine envelope (2026-11-04)

The external research boundary now has a **concrete, tested metadata adapter**
between the existing `scripts.research_job_queue` frozen request and a
`DurableResearchState.claim_next` attempt identity, using
`norisk_quant.external_queue_binding`.

A binding includes frozen queue digest, source commit, worker/attempt identity,
monotonic fencing token, frozen spec SHA256, provider-neutral external request,
and a canonical binding digest. An external receipt can be attached only with a
matching artifact checksum; it is never marked accepted.

**Important limitations:** The adapter is offline only and does not launch
LEAN, NautilusTrader or other providers. Its binding verification compares the
supplied claim but does not attest that the claim is STILL the current live
lease: callers must verify state ownership immediately before processing.
The source ZIP digest, repo code digest, provider build digest, allowed dataset,
and spec bytes each require external independent attestation. The adapter is
not a sandbox, code importer, worker supervisor, or result acceptance gate.
There is no live trading path, no automated recovery, and no production claim.
Do not upload private Gold data to this public repo.
