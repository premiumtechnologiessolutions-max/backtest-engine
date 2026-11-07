"""Fail-closed, pure-data envelope validation for future external adapters.

No imports of third-party engines, no IO, no execution. This validates *shape*
only and must never be interpreted as permission or evidence of market results.
"""
from __future__ import annotations

from collections.abc import Mapping
from scripts.static_external_adapter_registry import REGISTRY

SCHEMA = "NRFX_STATIC_ADAPTER_ENVELOPE_V1"
_MAX_ID = 96
_ALLOWED_KEYS = frozenset({"schema", "adapter", "request_id", "payload_schema", "payload"})


def validate_static_envelope(envelope: object) -> dict:
    """Return an inert summary or reject the entire envelope.

    Payload is limited to short literal schema field names; no paths, URLs,
    executable instructions, credentials, data rows or arbitrary objects.
    """
    if not isinstance(envelope, dict) or type(envelope) is not dict:
        raise ValueError("Envelope must be a plain dictionary")
    if set(envelope) != _ALLOWED_KEYS:
        raise ValueError("Missing or unknown envelope keys")
    if envelope["schema"] != SCHEMA or type(envelope["schema"]) is not str:
        raise ValueError("Unknown envelope schema")
    name = envelope["adapter"]
    if type(name) is not str or name not in REGISTRY:
        raise ValueError("Unknown adapter")
    request_id = envelope["request_id"]
    if (type(request_id) is not str or not 1 <= len(request_id) <= _MAX_ID
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in request_id)):
        raise ValueError("Invalid opaque request identifier")
    payload_schema = envelope["payload_schema"]
    if type(payload_schema) is not str or payload_schema not in REGISTRY[name].inputs:
        raise ValueError("Input schema not registered for adapter")
    payload = envelope["payload"]
    if type(payload) is not dict or set(payload) != {"field_names"}:
        raise ValueError("Only field-name declarations are permitted")
    fields = payload["field_names"]
    if (type(fields) is not list or not 1 <= len(fields) <= 32
            or any(type(field) is not str or not 1 <= len(field) <= 64
                   or not all(c.isascii() and (c.isalnum() or c == "_") for c in field)
                   for field in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError("Invalid field-name declarations")
    return {
        "schema": SCHEMA,
        "adapter": name,
        "request_id": request_id,
        "payload_schema": payload_schema,
        "field_count": len(fields),
        "status": "DESIGN_ONLY_DISABLED",
        "execution_authorized": False,
        "results_verified": False,
    }
