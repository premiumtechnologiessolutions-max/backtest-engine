"""Read-only, provenance-aware adapters to other No Risk FX research products."""

from .terminal_ticks import TerminalTickImport, import_terminal_ticks

__all__ = ("TerminalTickImport", "import_terminal_ticks")
