from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Side = Literal[1, -1]


@dataclass(frozen=True)
class Settings:
    ounces: float = 1.0
    roundtrip_cost_per_ounce: float = 0.40
    max_entry_delay_minutes: int = 1
    close_at_end: bool = True

    def __post_init__(self) -> None:
        if self.ounces <= 0:
            raise ValueError("ounces must be positive")
        if self.roundtrip_cost_per_ounce < 0:
            raise ValueError("roundtrip cost cannot be negative")
        if self.max_entry_delay_minutes < 0:
            raise ValueError("max entry delay cannot be negative")


@dataclass(frozen=True)
class Signal:
    # Signal exists only AFTER the candle ending at confirmed_at closes.
    confirmed_at: object
    side: Side
    stop_distance: float
    target_distance: float
    strategy: str = "unspecified"

    def __post_init__(self) -> None:
        if self.side not in (1, -1):
            raise ValueError("side must be +1 or -1")
        if self.stop_distance <= 0 or self.target_distance <= 0:
            raise ValueError("stop and target distances must be positive")


@dataclass
class Position:
    entry_at: object
    signal_at: object
    side: Side
    entry_price: float
    stop: float
    target: float
    strategy: str
    gap_minutes: int = 0


def serialize_settings(settings: Settings) -> dict:
    return asdict(settings)
