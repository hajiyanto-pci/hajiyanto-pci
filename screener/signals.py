"""Logika screening: volume spike, break resistance, skor potensi naik."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from screener.indicators import pct_change, resistance_level, rsi, sma
from screener.universe import from_yahoo_symbol


@dataclass
class Signal:
    symbol: str
    price: float
    volume: float
    volume_ratio: float
    resistance: float
    breakout_pct: float
    rsi: float
    ma: float
    above_ma: bool
    score: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_symbol(yahoo_symbol: str, df: pd.DataFrame, cfg: dict) -> Signal | None:
    vol_days = int(cfg.get("volume_avg_days", 20))
    vol_min = float(cfg.get("volume_spike_min", 1.5))
    res_lookback = int(cfg.get("resistance_lookback", 20))
    buffer_pct = float(cfg.get("breakout_buffer_pct", 0.0))
    rsi_period = int(cfg.get("rsi_period", 14))
    rsi_max = float(cfg.get("rsi_max", 75))
    ma_period = int(cfg.get("ma_period", 20))
    min_avg_vol = float(cfg.get("min_avg_volume", 500_000))
    min_price = float(cfg.get("min_price", 50))
    min_score = float(cfg.get("min_score", 60))

    if df is None or len(df) < max(vol_days, res_lookback, rsi_period, ma_period) + 2:
        return None

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    volume = df["Volume"].astype(float)

    last_close = float(close.iloc[-1])
    last_vol = float(volume.iloc[-1])
    if not np.isfinite(last_close) or last_close < min_price:
        return None

    avg_vol = float(volume.iloc[-(vol_days + 1) : -1].mean())
    if not np.isfinite(avg_vol) or avg_vol < min_avg_vol:
        return None

    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0
    resist = resistance_level(high, res_lookback)
    if resist is None or resist <= 0:
        return None

    break_level = resist * (1 + buffer_pct / 100.0)
    is_breakout = last_close >= break_level
    breakout_pct = pct_change(last_close, resist)

    rsi_series = rsi(close, rsi_period)
    last_rsi = float(rsi_series.iloc[-1]) if np.isfinite(rsi_series.iloc[-1]) else 50.0

    ma_series = sma(close, ma_period)
    last_ma = float(ma_series.iloc[-1]) if np.isfinite(ma_series.iloc[-1]) else last_close
    above_ma = last_close > last_ma

    # Hard filters for "akan naik" candidate:
    # 1) volume spike  2) break resistance  3) RSI tidak overbought
    if vol_ratio < vol_min:
        return None
    if not is_breakout:
        return None
    if last_rsi > rsi_max:
        return None

    score, reasons = _score(
        vol_ratio=vol_ratio,
        vol_min=vol_min,
        breakout_pct=breakout_pct,
        last_rsi=last_rsi,
        rsi_max=rsi_max,
        above_ma=above_ma,
        last_close=last_close,
        last_ma=last_ma,
    )

    if score < min_score:
        return None

    return Signal(
        symbol=from_yahoo_symbol(yahoo_symbol),
        price=round(last_close, 2),
        volume=round(last_vol, 0),
        volume_ratio=round(vol_ratio, 2),
        resistance=round(resist, 2),
        breakout_pct=round(breakout_pct, 2),
        rsi=round(last_rsi, 1),
        ma=round(last_ma, 2),
        above_ma=above_ma,
        score=round(score, 1),
        reasons=reasons,
    )


def _score(
    *,
    vol_ratio: float,
    vol_min: float,
    breakout_pct: float,
    last_rsi: float,
    rsi_max: float,
    above_ma: bool,
    last_close: float,
    last_ma: float,
) -> tuple[float, list[str]]:
    """Skor 0-100 berdasarkan kualitas breakout + volume + momentum."""
    reasons: list[str] = []
    score = 0.0

    # Volume (max 35)
    if vol_ratio >= vol_min * 3:
        score += 35
        reasons.append(f"Volume sangat tinggi ({vol_ratio:.1f}x rata-rata)")
    elif vol_ratio >= vol_min * 2:
        score += 28
        reasons.append(f"Volume tinggi ({vol_ratio:.1f}x rata-rata)")
    else:
        score += 20
        reasons.append(f"Volume di atas rata-rata ({vol_ratio:.1f}x)")

    # Breakout strength (max 30)
    if breakout_pct >= 3:
        score += 30
        reasons.append(f"Break resistance kuat (+{breakout_pct:.1f}%)")
    elif breakout_pct >= 1:
        score += 24
        reasons.append(f"Break resistance (+{breakout_pct:.1f}%)")
    else:
        score += 16
        reasons.append(f"Break resistance tipis (+{breakout_pct:.1f}%)")

    # RSI sweet spot (max 20): momentum naik tapi belum overbought
    if 50 <= last_rsi <= 65:
        score += 20
        reasons.append(f"RSI sehat ({last_rsi:.0f})")
    elif 45 <= last_rsi < 50 or 65 < last_rsi <= rsi_max:
        score += 12
        reasons.append(f"RSI masih ok ({last_rsi:.0f})")
    else:
        score += 6
        reasons.append(f"RSI ({last_rsi:.0f})")

    # Trend vs MA (max 15)
    if above_ma:
        ma_gap = pct_change(last_close, last_ma)
        score += 15 if ma_gap >= 1 else 10
        reasons.append("Harga di atas MA")
    else:
        score += 0
        reasons.append("Harga di bawah MA")

    return min(score, 100.0), reasons


def screen_all(histories: dict[str, pd.DataFrame], cfg: dict) -> list[Signal]:
    signals: list[Signal] = []
    for sym, df in histories.items():
        sig = evaluate_symbol(sym, df, cfg)
        if sig is not None:
            signals.append(sig)
    signals.sort(key=lambda s: s.score, reverse=True)
    return signals
