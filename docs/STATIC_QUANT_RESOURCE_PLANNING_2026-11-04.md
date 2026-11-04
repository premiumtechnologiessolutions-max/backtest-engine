# Quant campaign static resource planner (construction only)

This is the second component of the quant engine unified workflow:
`campaign_blueprint.freeze_blueprint()` freezes the whole research DAG;
`static_resource_plan.plan_resource_waves()` assigns every planned node to
a deterministic resource-bounded wave. Dependencies only resolve in **earlier
planned waves**, never in a simultaneously scheduled peer task.

The planner accounts for maximum parallel workers, heuristic memory/scratch
capacity, a bounded intended runtime and the distinct roles of market data
causal alignment, strategy compilation, reference engines, comparison,
risk, AI feedback and reports. No subprocesses, database writes, provider
calls, LLM invocations or real market data access occur.

**Engineering caveat:** RAM, scratch and stage durations are *unmeasured
estimates*, not proof a real full-year LEAN/Nautilus workload fits. Declared
wall budget failure is explicitly flagged as requiring replanning. Real
runtime profiles and process isolation cannot be measured before owner
approval for external engine execution; construction CI uses synthetics only.

This does NOT implement a process supervisor, acceptance gate, UI or
actual resource-enforced scheduler. It is an inert design artifact for
future tested integration.
