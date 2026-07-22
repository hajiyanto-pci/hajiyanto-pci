"""Indikator teknikal sederhana tanpa dependensi TA-Lib."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def resistance_level(high: pd.Series, lookback: int) -> float | None:
    """Highest high over lookback bars excluding the latest bar."""
    if len(high) < lookback + 1:
        return None
    window = high.iloc[-(lookback + 1) : -1]
    value = float(window.max())
    return value if np.isfinite(value) else None


def pct_change(a: float, b: float) -> float:
    if b == 0 or not np.isfinite(a) or not np.isfinite(b):
        return 0.0
    return (a - b) / b * 100.0
