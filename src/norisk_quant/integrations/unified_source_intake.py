"""Read-only end-to-end bridge: private Terminal ticks -> canonical Data Hub.

Requires B01 terminal_ticks and B02 source_registry adapters. All input stays
in process memory. Never auto-trades, sends network requests, stages original
broker files in a public repository, chooses strategies, or combines P/L.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from norisk_quant.integrations.terminal_ticks import (
    MAX_BYTES, import_terminal_ticks,
)
from norisk_quant.source_registry import (
    SourceRecord, register_terminal_tick_evidence,
)


@dataclass(frozen=True)
class PrivateTerminalIngest:
    """Quotes remain local. Browser/UI may receive ONLY public_metadata()."""

    ticks: pd.DataFrame
    record: SourceRecord

    def public_metadata(self) -> dict:
        """Sanitized, read-only evidence without quote arrays/account scope."""
        return self.record.public_summary()


def ingest_terminal_snapshot(raw_bytes: bytes, *, allow_synthetic: bool = False) -> PrivateTerminalIngest:
    """Validate private input once, and bind the exact quote evidence to registry.

    No username, password, broker login, credentials, raw ledger or original
    Gold ZIP may enter this function. No fee scenario is calculated.
    """
    verified_quotes = import_terminal_ticks(raw_bytes, allow_synthetic=allow_synthetic)
    record = register_terminal_tick_evidence(
        verified_quotes.evidence, permit_synthetic=allow_synthetic,
    )
    if record.rows != len(verified_quotes.ticks):
        raise ValueError("Inconsistent Terminal-to-Data-Hub quote row count")
    if record.observed_quote_sha256 != verified_quotes.evidence["quote_context_sha256"]:
        raise ValueError("Terminal-to-Data-Hub quote fingerprint mismatch")
    if record.source_file_sha256 != verified_quotes.evidence["source_bytes_sha256"]:
        raise ValueError("Terminal-to-Data-Hub source-byte fingerprint mismatch")
    if record.account_currency != verified_quotes.evidence["account_currency_label"]:
        raise ValueError("Terminal-to-Data-Hub quote/account currency mismatch")
    if record.first_utc != verified_quotes.ticks.index[0].isoformat() or record.last_utc != verified_quotes.ticks.index[-1].isoformat():
        raise ValueError("Terminal-to-Data-Hub normalized UTC interval mismatch")
    return PrivateTerminalIngest(ticks=verified_quotes.ticks, record=record)


def inspect_local_file(path: str | Path, *, allow_synthetic: bool = False) -> dict:
    """Read one private, size-bounded snapshot and return sanitized metadata.

    Does not write the file anywhere, never includes the original private
    provider-scope field or quote values. Caller must protect local file
    permissions, and read bytes must never be uploaded to public GitHub.
    """
    file = Path(path)
    if not file.is_file() or file.is_symlink():
        raise ValueError("Expected a regular non-symlink private Terminal snapshot")
    if not 0 < file.stat().st_size <= MAX_BYTES:
        raise ValueError("Private snapshot is empty or exceeds 80 MB")
    product = ingest_terminal_snapshot(file.read_bytes(), allow_synthetic=allow_synthetic)
    metadata = product.public_metadata()
    return {
        "data_hub": metadata,
        "audit": {
            "execution": "NONE",
            "pricing": "SOURCE_QUOTES_ONLY",
            "cost_model": "NOT_APPLIED_DATA_ONLY",
            "source_authentication": "NOT_VERIFIED",
            "fees": "NOT_APPLIED",
            "independent_oos": False,
            "profitability_verified": False,
            "broker_fill_parity": False,
            "real_trading": False,
        },
    }
