# Inert quant research campaign sharding up to 4,096 strategies

The No Risk FX research platform now has a **construction blueprint** for
large research universes, without running a single strategy.

`campaign_sharding.freeze_sharded_campaign(spec)` splits a canonical
strategy universe into SHA-pinned small DAG shards. Each shard uses the
same immutable data/code/spec identities and resource-limited static plan.
The maximum shard size depends on combined reference-engine + AI-reviewer
fanout, never exceeds 32 strategy hypotheses, and each graph stays below
the strategy*provider ceiling in `campaign_blueprint`.

**Important statistical caveat:** splitting a campaign across shards does
NOT split the family of hypotheses for multiple-testing purposes. Global
false-discovery controls and selection penalties must later be applied to
ALL candidates, including rejected ones. Here that step is explicitly
UNIMPLEMENTED and no positive research result is claimed.

No external engine, AI agent, quote ZIP or subprocess is ever run by
freezing/sharding. No real campaign was executed, and there is no
production scheduling or source-reconciliation evidence.
