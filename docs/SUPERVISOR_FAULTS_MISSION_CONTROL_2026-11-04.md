# Synthetic supervisor failure visibility in control-plane health

The read-only SQLite operational health gate audits ALL synthetic worker
fault receipts inside its existing consistent WAL snapshot. A forged or
modified receipt invalidates the whole control plane. A valid but unverified
fault record requires operator attention; it is never accepted research.

Quant Mission Control displays total supervised synthetic test receipts
and failure classifications, explicitly distinguished from vendor runs.
No original Gold dataset, external engine, research campaign or trading
account is accessed. These are OS engineering tests only.
