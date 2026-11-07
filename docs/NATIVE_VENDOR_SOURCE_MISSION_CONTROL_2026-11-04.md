# Mission Control native-source evidence

The read-only SQLite operations gate audits every immutable LEAN/Nautilus
vendor-export source manifest together with the existing queue, receipts,
inert DAG and cross-engine parity records. Any source manifest corruption
marks the whole control plane INVALID. Intact source evidence remains
unverified and requires operator attention; it does NOT authorize execution.

The offline browser dashboard now displays the number of native source
manifests and vendor exports. It makes no claim that these are genuine
external runner outputs or independently verified market results.

All tests use synthetic metadata and rows, not original Gold data.
