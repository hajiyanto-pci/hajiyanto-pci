"""Indikator teknikal multi-faktor tanpa TA-Lib."""

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


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    denom = (highest - lowest).replace(0, np.nan)
    k = 100 * (close - lowest) / denom
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return k, d


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def chaikin_money_flow(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:
    """CMF: proksi aliran dana / bandarmology sederhana dari OHLCV."""
    hl = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm.fillna(0.0) * volume.fillna(0.0)
    vol_sum = volume.rolling(window=period, min_periods=period).sum().replace(0, np.nan)
    return mfv.rolling(window=period, min_periods=period).sum() / vol_sum


def money_flow_index(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_mf = typical * volume.fillna(0.0)
    delta = typical.diff()
    pos = raw_mf.where(delta > 0, 0.0)
    neg = raw_mf.where(delta < 0, 0.0)
    pos_sum = pos.rolling(window=period, min_periods=period).sum()
    neg_sum = neg.rolling(window=period, min_periods=period).sum().replace(0, np.nan)
    mfr = pos_sum / neg_sum
    return 100 - (100 / (1 + mfr))


def bollinger(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


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
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume.fillna(0.0)).cumsum()


def is_accumulating(
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 10,
) -> tuple[bool, str]:
    """Deteksi akumulasi: OBV naik + volume beli > volume jual di lookback."""
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
        return True, f"Akumulasi OBV (vol beli {ratio:.1f}x vol jual)"
    if obv_up:
        return True, "Akumulasi ringan (OBV naik)"
    return False, "Belum akumulasi (OBV belum naik)"


def bandar_flow_score(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    *,
    cmf_period: int = 20,
    mfi_period: int = 14,
) -> tuple[bool, float, str]:
    """Proksi bandarmology dari money flow (bukan data broker asli).

    Return (ok, score_0_to_15, note).
    """
    cmf = chaikin_money_flow(high, low, close, volume, cmf_period)
    mfi = money_flow_index(high, low, close, volume, mfi_period)
    last_cmf = float(cmf.iloc[-1]) if len(cmf) and np.isfinite(cmf.iloc[-1]) else 0.0
    last_mfi = float(mfi.iloc[-1]) if len(mfi) and np.isfinite(mfi.iloc[-1]) else 50.0

    points = 0.0
    notes = []
    if last_cmf >= 0.15:
        points += 9
        notes.append(f"CMF kuat ({last_cmf:.2f})")
    elif last_cmf >= 0.05:
        points += 6
        notes.append(f"CMF positif ({last_cmf:.2f})")
    elif last_cmf > 0:
        points += 3
        notes.append(f"CMF tipis+ ({last_cmf:.2f})")
    else:
        notes.append(f"CMF lemah ({last_cmf:.2f})")

    if 50 <= last_mfi <= 75:
        points += 6
        notes.append(f"MFI sehat ({last_mfi:.0f})")
    elif 40 <= last_mfi < 50 or 75 < last_mfi <= 85:
        points += 3
        notes.append(f"MFI ok ({last_mfi:.0f})")
    else:
        notes.append(f"MFI ({last_mfi:.0f})")

    ok = last_cmf > 0 and last_mfi >= 45
    return ok, min(points, 15.0), "Money-flow/bandar-proxy: " + "; ".join(notes)
