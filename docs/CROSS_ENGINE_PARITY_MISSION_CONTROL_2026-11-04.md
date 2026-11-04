# Cross-engine evidence durability in the Quant Engine mission control

The SQLite health gate now audits every unverified cross-engine parity
report in the same read-only WAL transaction as the original queue,
receipt inbox and inert campaign DAG registry. Any altered report SHA,
attempt identity, ledger-summary body or false acceptance statement
makes the entire gate INVALID. A consistent but unverified comparison
marks the control plane OPERATOR_ATTENTION rather than HEALTHY.

The offline mission-control snapshot and browser UI display counts of
unverified cross-engine reports and discrepancies. They never show
engine execution, strategy approval or accepted research results.

Native LEAN/Nautilus live/external source provenance, fill-event
reconciliation and independent OOS acceptance are still missing.
