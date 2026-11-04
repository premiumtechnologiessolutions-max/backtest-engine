"""Deterministic, inert construction-job identity. Never launches a job."""
import hashlib
import json

from scripts.construction_job_admission import admit


def fingerprint(spec):
    """Hash an admitted immutable descriptor, not an executable command."""
    accepted = admit(spec)
    canonical = {key: accepted[key] for key in
                 ("kind", "name", "source_commit", "fixture")}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
    return {"job_fingerprint": hashlib.sha256(payload).hexdigest(),
            "status": "INERT_NOT_QUEUED",
            "execution_started": False, "market_data_accessed": False,
            "source_commit": canonical["source_commit"]}
