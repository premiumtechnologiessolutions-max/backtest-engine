"""B08: one private, read-only operator view across the NoRiskFX research stack.

Combines:
 * B01/B03 Terminal v0.19.1 private tick intake and provenance
 * B02/B05/B07 original Gold M1 source catalog
 * B04/B06 local research queue metadata (NOT private work payloads)

No web server, no HTTP endpoint, no broker calls, no trading execution, no
data-source promotion to validated strategy evidence, and no persistent
market-data storage. A caller must enforce private operator authorization
before exposing any snapshot. Do not pass raw snapshots to client browsers.
"""
from __future__ import annotations

from typing import Any

from .integrations.unified_source_intake import ingest_terminal_snapshot
from .research_control_plane import ResearchQueue
from .source_registry import (
    SourceRegistry, verify_record_manifest,
)


class UnifiedResearchPlatform:
    """In-memory source metadata catalog + existing durable research queue.

    Only the queue itself owns persistent work state. The catalog is an
    intentionally nonpersistent private in-process view; a future
    authenticated service must version and persist source records properly.
    """

    def __init__(self, *, queue: ResearchQueue, sources: SourceRegistry | None = None) -> None:
        if not isinstance(queue, ResearchQueue):
            raise TypeError("ResearchQueue is required")
        if sources is not None and not isinstance(sources, SourceRegistry):
            raise TypeError("SourceRegistry is required")
        self.queue = queue
        self.sources = sources if sources is not None else SourceRegistry()

    def observe_terminal_snapshot(self, original_private_json: bytes, *,
                                  allow_synthetic: bool = False) -> dict[str, Any]:
        """Read, validate and register private ticks as *metadata only*.

        Terminal data is never silently substituted for the original Gold
        M1 archive, and never unlocks the backtest runner.
        """
        result = ingest_terminal_snapshot(
            original_private_json, allow_synthetic=allow_synthetic,
        )
        self.sources.add(result.record)
        return result.public_metadata()

    def index_declared_source_manifest(self, internal_manifest: dict) -> dict[str, Any]:
        """Stage manifest metadata. Does NOT hash/replay source file bytes.

        All local source/strategy lineage must still be proven independently
        through B05/B07 preflight and the B06 private worker.
        """
        record = verify_record_manifest(internal_manifest)
        self.sources.add(record)
        return record.public_summary()

    def operator_snapshot(self) -> dict[str, Any]:
        """Redacted operator-only status. NO raw quotes/worker tokens/P&L.

        This method does not implement authorization. Future private
        Terminal gateway MUST require existing authentication before call.
        """
        sources = self.sources.summaries()
        counts = self.queue.counts()
        return {
            "schema": "NRFX_UNIFIED_RESEARCH_PLATFORM_OPERATOR_V1",
            "data_hub": {
                "sources": sources,
                "registered_metadata_sources": len(sources),
                "persisted_source_registry": False,
                "raw_quotes_in_snapshot": False,
                "original_gold_source_file_verified_here": False,
            },
            "research_control": {
                "counts": counts,
                "operator_paused": counts["paused"],
                "hypothesis_payloads_visible": False,
                "worker_lease_tokens_visible": False,
                "agent_authorized_to_certify_profit": False,
            },
            "execution": {
                "canonical_runner": "OPERATOR_GATED_POSIX_ONLY",
                "strategy_execution_requested": False,
                "mt5_order_connection": False,
                "oracle_deployment": False,
                "broker_fill_parity": False,
                "independent_oos": False,
                "profitability_verified": False,
                "approved_for_live": False,
            },
            "review_gates": {
                "source_lineage": "REQUIRED_PER_EXPERIMENT",
                "strategy_implementation_parity": "REQUIRED",
                "canonical_ledger_audit": "REQUIRED",
                "true_forward_out_of_sample": "REQUIRED",
                "market_gap_calendar_review": "REQUIRED",
                "private_operator_authentication": "NOT_IMPLEMENTED_BY_THIS_VIEW",
            },
        }
