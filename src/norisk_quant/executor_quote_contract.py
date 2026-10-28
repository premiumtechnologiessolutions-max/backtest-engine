"""Fail-closed M1 OHLC schema gate shared by reference, fast and limit replay.

Source normalization may explicitly parse raw CSV/JSON quote strings, but an
already constructed execution DataFrame must not silently coerce text or
boolean quotes into prices. This checks dtypes only; each executor retains
its own finite-price and OHLC geometry validation.
"""
from __future__ import annotations

import pandas as pd


def require_numeric_execution_ohlc(minutes: pd.DataFrame) -> None:
    """Reject duplicate, missing, text and boolean M1 OHLC columns pre-replay."""
    if not isinstance(minutes, pd.DataFrame):
        raise ValueError("Execution M1 quotes must be a DataFrame")
    if minutes.columns.has_duplicates:
        raise ValueError("Execution M1 OHLC columns must be unique")
    for name in ("o", "h", "l", "c"):
        if name not in minutes.columns:
            raise ValueError(f"Execution M1 missing {name}")
        dtype = minutes[name].dtype
        if (not pd.api.types.is_numeric_dtype(dtype)
                or pd.api.types.is_bool_dtype(dtype)):
            raise ValueError(
                f"Execution M1 {name} must have numeric non-boolean dtype"
            )
