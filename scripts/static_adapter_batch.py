"""Pure-data batch preflight; never schedules or executes adapter requests."""
from __future__ import annotations

from scripts.static_adapter_envelope import validate_static_envelope

MAX_BATCH = 32


def validate_static_batch(envelopes: object) -> dict:
    """Reject an entire batch on any malformed or duplicate request ID."""
    if type(envelopes) is not list or not 1 <= len(envelopes) <= MAX_BATCH:
        raise ValueError("Batch must be a plain nonempty list of at most 32")
    seen: set[str] = set()
    adapters: set[str] = set()
    for envelope in envelopes:
        result = validate_static_envelope(envelope)
        request_id = result["request_id"]
        if request_id in seen:
            raise ValueError("Duplicate request identifier in batch")
        seen.add(request_id)
        adapters.add(result["adapter"])
    return {
        "status": "DESIGN_ONLY_DISABLED",
        "request_count": len(seen),
        "adapter_count": len(adapters),
        "execution_authorized": False,
        "results_verified": False,
    }
