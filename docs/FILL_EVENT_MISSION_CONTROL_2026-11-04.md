# Mission Control: vendor fill-event accounting evidence

The offline Quant dashboard now displays the number of optional
unverified vendor fill-event reconciliations and total supplied fill
events checked. Both counts come from the same read-only SQLite integrity
gate that audits source SHA, ledger SHA, attempt identity, and fill report
SHA. The frontend explicitly labels these counts as unverified.

This is NOT independent confirmation that a real LEAN/Nautilus process,
Gold market archive, broker or historical event source produced them.
No execution or research approval is authorized by the dashboard.
