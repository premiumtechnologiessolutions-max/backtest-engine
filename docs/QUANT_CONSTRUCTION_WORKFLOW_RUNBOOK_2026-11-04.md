# No Risk FX Quant Engine — reproducible construction workflow

The following commands operate on **specification metadata only**, not
Gold quotes, external providers, live orders or backtests.

```bash
python -m scripts.quant_freeze_campaign \
  --spec /private/synthetic_or_planned_spec.json \
  --out /private/frozen_quant_design.json

python -m scripts.quant_construction_snapshot \
  --design /private/frozen_quant_design.json \
  > /private/mission_control_status.json
```

Then open `web/quant-control/index.html` in your browser and select
`mission_control_status.json` in **Load local status JSON**.

The freeze command validates the full global strategy universe, pinned
source/strategy/spec identifiers, allowed engines/AI reviewers, resource
budgets and execution freeze. It writes canonical JSON using exclusive
atomic publish (hard link from a synced temporary file); a different
existing artifact is never overwritten. Repeated identical requests are
idempotent. Output stays local, not uploaded to GitHub.

The snapshot CLI checks the frozen design and can optionally probe an
existing SQLite database read-only. The dashboard itself has no network
access and will never show market readiness.

The declared Gold source hash is a **metadata identity only** in this
construction workflow — source bytes are not opened or verified here.
This is not a working market engine or permission to start research.
