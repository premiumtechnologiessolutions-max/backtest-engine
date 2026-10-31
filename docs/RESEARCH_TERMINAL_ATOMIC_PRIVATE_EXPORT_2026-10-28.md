# Quant Research Terminal — atomic private HTML export (2026-10-28)

The offline terminal now writes **all** generated HTML through `scripts/research_terminal_export.py`, including the optional queue/month-plan view. This fixes the prior direct `Path.write_text` behavior, which could leave a partial export on failure and could create a world-readable file under a normal POSIX umask even when local research job fingerprints were opted in.

- POSIX exports are written to a temporary file with mode **0600**, flushed and fsynced, then atomically replaced. An existing valid report is retained if rendering or the replacement step fails; temporary files are cleaned up.
- A symlinked destination or parent and pre-existing hardlinked/nonregular destination are rejected. Only `.html` output names are accepted to reduce accidental overwrites of registry JSON or CSV evidence.
- No web server, network transfer, private XAUUSD source, worker, broker access or execution is introduced. Windows ACL protection and hostile concurrent directory replacement are **not** certified; store local reports in a private directory on a trusted workstation.
- Tests cover owner-only mode, repeated export, symlink/hardlink rejection, atomic failure recovery, extension restrictions and CLI integration. Run `python -m pytest -q tests/test_research_terminal_export.py`.

Research accounting is **unchanged**: no new Gold ZIP M1 backtests, no monthly P/L observations, no source-verified prospective months, no OOS certification or approved strategies. The frozen research registry remains the sole accounting source. Keep PR #1 Draft/unmerged.
