"""Logika screening: volume spike, break resistance, skor potensi naik."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from screener.indicators import pct_change, resistance_level, rsi, sma
from screener.schedule import session_progress
from screener.universe import from_yahoo_symbol

JAKARTA = ZoneInfo("Asia/Jakarta")


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
    mode: str = "eod"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bar_date(idx_value) -> datetime.date:
    ts = pd.Timestamp(idx_value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(JAKARTA)
    else:
        ts = ts.tz_convert(JAKARTA)
    return ts.date()


def _prepare_frame(df: pd.DataFrame, mode: str, now: datetime | None = None) -> pd.DataFrame:
    """Morning memakai bar lengkap terakhir; eod/midday pakai bar terbaru."""
    if df is None or df.empty:
        return df
    mode = (mode or "eod").lower()
    if mode != "morning":
        return df

    now = datetime.now(JAKARTA) if now is None else now
    today = now.astimezone(JAKARTA).date() if now.tzinfo else now.replace(tzinfo=JAKARTA).date()
    last_date = _bar_date(df.index[-1])
    # Jika candle hari ini sudah ada tapi belum EOD, pakai H-1 untuk watchlist pagi.
    if last_date >= today and len(df) >= 2:
        return df.iloc[:-1].copy()
    return df


def evaluate_symbol(
    yahoo_symbol: str,
    df: pd.DataFrame,
    cfg: dict,
    *,
    now: datetime | None = None,
) -> Signal | None:
    mode = str(cfg.get("mode", "eod")).lower()
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

    # Midday lebih ketat: kurangi noise early alert
    if mode == "midday":
        vol_min = float(cfg.get("midday_volume_spike_min", max(vol_min, 2.0)))
        min_score = float(cfg.get("midday_min_score", max(min_score, 70)))

    work = _prepare_frame(df, mode, now=now)
    need = max(vol_days, res_lookback, rsi_period, ma_period) + 2
    if work is None or len(work) < need:
        return None

    close = work["Close"].astype(float)
    high = work["High"].astype(float)
    volume = work["Volume"].astype(float)

    last_close = float(close.iloc[-1])
    last_vol = float(volume.iloc[-1])
    if not np.isfinite(last_close) or last_close < min_price:
        return None

    avg_vol = float(volume.iloc[-(vol_days + 1) : -1].mean())
    if not np.isfinite(avg_vol) or avg_vol < min_avg_vol:
        return None

    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0
    projected_note = None
    if mode == "midday":
        progress = session_progress(now)
        # Hindari proyeksi ekstrem di awal sesi
        progress = max(progress, 0.25)
        projected_vol = last_vol / progress
        vol_ratio = projected_vol / avg_vol if avg_vol > 0 else 0.0
        projected_note = (
            f"Volume terproyeksi ~{vol_ratio:.1f}x "
            f"(aktual {last_vol / avg_vol:.1f}x @ {progress:.0%} sesi)"
        )

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

    if mode == "morning":
        reasons.insert(0, "Watchlist dari breakout H-1 (siap pantau di open)")
    elif mode == "midday":
        reasons.insert(0, "Early alert intraday (belum final sampai EOD)")
        if projected_note:
            reasons.insert(1, projected_note)
        # Penalti kecil karena belum confirmed
        score = max(0.0, score - 5)
    else:
        reasons.insert(0, "Sinyal EOD confirmed (close & volume final)")

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
        mode=mode,
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

    if vol_ratio >= vol_min * 3:
        score += 35
        reasons.append(f"Volume sangat tinggi ({vol_ratio:.1f}x rata-rata)")
    elif vol_ratio >= vol_min * 2:
        score += 28
        reasons.append(f"Volume tinggi ({vol_ratio:.1f}x rata-rata)")
    else:
        score += 20
        reasons.append(f"Volume di atas rata-rata ({vol_ratio:.1f}x)")

    if breakout_pct >= 3:
        score += 30
        reasons.append(f"Break resistance kuat (+{breakout_pct:.1f}%)")
    elif breakout_pct >= 1:
        score += 24
        reasons.append(f"Break resistance (+{breakout_pct:.1f}%)")
    else:
        score += 16
        reasons.append(f"Break resistance tipis (+{breakout_pct:.1f}%)")

    if 50 <= last_rsi <= 65:
        score += 20
        reasons.append(f"RSI sehat ({last_rsi:.0f})")
    elif 45 <= last_rsi < 50 or 65 < last_rsi <= rsi_max:
        score += 12
        reasons.append(f"RSI masih ok ({last_rsi:.0f})")
    else:
        score += 6
        reasons.append(f"RSI ({last_rsi:.0f})")

    if above_ma:
        ma_gap = pct_change(last_close, last_ma)
        score += 15 if ma_gap >= 1 else 10
        reasons.append("Harga di atas MA")
    else:
        score += 0
        reasons.append("Harga di bawah MA")

    return min(score, 100.0), reasons


def screen_all(
    histories: dict[str, pd.DataFrame],
    cfg: dict,
    *,
    now: datetime | None = None,
) -> list[Signal]:
    signals: list[Signal] = []
    for sym, df in histories.items():
        sig = evaluate_symbol(sym, df, cfg, now=now)
        if sig is not None:
            signals.append(sig)
    signals.sort(key=lambda s: s.score, reverse=True)
    return signals
