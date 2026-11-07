# Complete inert Quant Engine construction workflow

1. Freeze a private JSON campaign design into a deterministic SHA-pinned
   artifact with scripts.quant_freeze_campaign.
2. Register all sharded research DAG nodes atomically into the durable
   SQLite construction registry with scripts.quant_register_campaign.
3. Use the registry audit subcommand to independently inspect every
   persisted node and dependency via the operations integrity gate.
4. Produce a read-only snapshot with scripts.quant_construction_snapshot
   and load it in web/quant-control/index.html.

Commands:
python -m scripts.quant_freeze_campaign --spec /private/spec.json --out /private/design.json
python -m scripts.quant_register_campaign register --design /private/design.json --database /private/control.sqlite3
python -m scripts.quant_register_campaign audit --database /private/control.sqlite3
python -m scripts.quant_construction_snapshot --design /private/design.json --database /private/control.sqlite3

None of these commands starts a worker, calls LEAN/Nautilus, opens Gold
market data, accepts strategy results, or authorizes live trading. They
are an ENGINEERING-ONLY workflow for the future integrated research system.