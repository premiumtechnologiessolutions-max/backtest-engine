# Inert batch adapter receipt manifest

`scripts/static_adapter_batch_manifest.py` binds up to 32 registered
design-only adapter envelopes to a deterministic SHA-256 manifest. The
manifest contains the **ordered** request IDs and their individually
bound receipts. Both producer and validator fail closed on malformed
input, duplicates, reordering, missing receipts, content drift, and
attempts to set execution or results flags.

It deliberately does **not** dispatch work, call adapters, authenticate
vendor provenance, or attest that an engine has executed. The checksum
only detects drift relative to caller-supplied content, not malicious
replacement of both manifest and source. Independent provenance,
authorization, and operational isolation remain outstanding acceptance
requirements. Tests use literal synthetic schema fields only.
