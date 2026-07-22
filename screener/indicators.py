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


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume sederhana."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume.fillna(0.0)).cumsum()


def is_accumulating(
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 10,
) -> tuple[bool, str]:
    """Deteksi akumulasi: OBV naik + volume beli > volume jual di lookback.

    Return (flag, penjelasan singkat).
    """
    if len(close) < lookback + 2 or len(volume) < lookback + 2:
        return False, "Data akumulasi kurang"

    obv_series = obv(close, volume)
    obv_now = float(obv_series.iloc[-1])
    obv_prev = float(obv_series.iloc[-(lookback + 1)])
    obv_up = np.isfinite(obv_now) and np.isfinite(obv_prev) and obv_now > obv_prev

    window_close = close.iloc[-lookback:]
    window_vol = volume.iloc[-lookback:]
    up_mask = window_close.diff().fillna(0.0) > 0
    buy_vol = float(window_vol[up_mask].sum())
    sell_vol = float(window_vol[~up_mask].sum())
    buy_dominant = sell_vol == 0 or (buy_vol / max(sell_vol, 1.0)) >= 1.1

    if obv_up and buy_dominant:
        ratio = buy_vol / max(sell_vol, 1.0)
        return True, f"Akumulasi (OBV naik, vol beli {ratio:.1f}x vol jual)"
    if obv_up:
        return True, "Akumulasi ringan (OBV naik)"
    return False, "Belum akumulasi (OBV belum naik)"
