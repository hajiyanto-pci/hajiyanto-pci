"""Logika screening: volume, MA, akumulasi, break resistance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from screener.indicators import (
    is_accumulating,
    pct_change,
    resistance_level,
    rsi,
    sma,
)
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
    accumulating: bool
    breakout: bool
    volume_ok: bool
    score: float
    reasons: list[str]
    checklist: dict[str, bool] = field(default_factory=dict)
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


def parse_as_of(value: str | None, *, now: datetime | None = None) -> datetime.date | None:
    """Parse 'yesterday' / 'kemarin' / 'YYYY-MM-DD' menjadi tanggal Jakarta.

    'kemarin' = sesi bursa sebelumnya (lewati Sabtu/Minggu).
    """
    from datetime import date, timedelta

    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip().lower()
    if now is None:
        now = datetime.now(JAKARTA)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JAKARTA)
    else:
        now = now.astimezone(JAKARTA)

    if raw in {"yesterday", "kemarin", "h-1", "prev", "last", "last-session"}:
        d = now.date() - timedelta(days=1)
        # Lewati weekend; hari libur nasional tetap perlu tanggal eksplisit
        while d.weekday() >= 5:  # 5=Sabtu, 6=Minggu
            d -= timedelta(days=1)
        return d
    return datetime.strptime(raw, "%Y-%m-%d").date()


def slice_as_of(df: pd.DataFrame, as_of: datetime.date | None) -> pd.DataFrame:
    """Potong data sampai tanggal as_of (inklusif), untuk analisa hari kemarin/dll."""
    if df is None or df.empty or as_of is None:
        return df
    mask = [_bar_date(i) <= as_of for i in df.index]
    return df.loc[mask].copy()


def _prepare_frame(
    df: pd.DataFrame,
    mode: str,
    now: datetime | None = None,
    as_of: datetime.date | None = None,
) -> pd.DataFrame:
    """Siapkan frame: as_of (analisa tanggal) atau morning (pakai H-1)."""
    if df is None or df.empty:
        return df

    if as_of is not None:
        return slice_as_of(df, as_of)

    mode = (mode or "eod").lower()
    if mode != "morning":
        return df

    now = datetime.now(JAKARTA) if now is None else now
    today = now.astimezone(JAKARTA).date() if now.tzinfo else now.replace(tzinfo=JAKARTA).date()
    last_date = _bar_date(df.index[-1])
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
    as_of = cfg.get("as_of")
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
    accum_lookback = int(cfg.get("accumulation_lookback", 10))
    require_above_ma = bool(cfg.get("require_above_ma", True))
    require_accumulation = bool(cfg.get("require_accumulation", True))

    if mode == "midday" and as_of is None:
        vol_min = float(cfg.get("midday_volume_spike_min", max(vol_min, 2.0)))
        min_score = float(cfg.get("midday_min_score", max(min_score, 70)))

    work = _prepare_frame(df, mode, now=now, as_of=as_of)
    need = max(vol_days, res_lookback, rsi_period, ma_period, accum_lookback) + 2
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

    raw_vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0
    vol_ratio = raw_vol_ratio
    projected_note = None
    if mode == "midday":
        progress = session_progress(now)
        progress = max(progress, 0.25)
        projected_vol = last_vol / progress
        vol_ratio = projected_vol / avg_vol if avg_vol > 0 else 0.0
        projected_note = (
            f"Volume terproyeksi ~{vol_ratio:.1f}x "
            f"(aktual {raw_vol_ratio:.1f}x @ {progress:.0%} sesi)"
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

    accumulating, accum_note = is_accumulating(close, volume, lookback=accum_lookback)
    volume_ok = vol_ratio >= vol_min

    checklist = {
        "volume": volume_ok,
        "above_ma": above_ma,
        "accumulation": accumulating,
        "breakout": is_breakout,
    }

    # Hard filters sesuai kriteria user
    if not volume_ok:
        return None
    if not is_breakout:
        return None
    if require_above_ma and not above_ma:
        return None
    if require_accumulation and not accumulating:
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
        accumulating=accumulating,
        accum_note=accum_note,
        last_close=last_close,
        last_ma=last_ma,
    )

    if as_of is not None:
        bar_day = _bar_date(work.index[-1])
        reasons.insert(0, f"Analisa as-of {as_of.isoformat()} (bar {bar_day.isoformat()})")
    elif mode == "morning":
        reasons.insert(0, "Watchlist dari breakout H-1 (siap pantau di open)")
    elif mode == "midday":
        reasons.insert(0, "Early alert intraday (belum final sampai EOD)")
        if projected_note:
            reasons.insert(1, projected_note)
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
        accumulating=accumulating,
        breakout=is_breakout,
        volume_ok=volume_ok,
        score=round(score, 1),
        reasons=reasons,
        checklist=checklist,
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
    accumulating: bool,
    accum_note: str,
    last_close: float,
    last_ma: float,
) -> tuple[float, list[str]]:
    """Skor 0-100: volume + breakout + RSI + MA + akumulasi."""
    reasons: list[str] = []
    score = 0.0

    # Volume (max 30)
    if vol_ratio >= vol_min * 3:
        score += 30
        reasons.append(f"Volume sangat tinggi ({vol_ratio:.1f}x rata-rata)")
    elif vol_ratio >= vol_min * 2:
        score += 24
        reasons.append(f"Volume tinggi ({vol_ratio:.1f}x rata-rata)")
    else:
        score += 16
        reasons.append(f"Volume di atas rata-rata ({vol_ratio:.1f}x)")

    # Breakout (max 25)
    if breakout_pct >= 3:
        score += 25
        reasons.append(f"Break resistance kuat (+{breakout_pct:.1f}%)")
    elif breakout_pct >= 1:
        score += 20
        reasons.append(f"Break resistance (+{breakout_pct:.1f}%)")
    else:
        score += 14
        reasons.append(f"Break resistance tipis (+{breakout_pct:.1f}%)")

    # Akumulasi (max 20)
    if accumulating:
        score += 20
        reasons.append(accum_note)
    else:
        score += 0
        reasons.append(accum_note)

    # RSI (max 15)
    if 50 <= last_rsi <= 65:
        score += 15
        reasons.append(f"RSI sehat ({last_rsi:.0f})")
    elif 45 <= last_rsi < 50 or 65 < last_rsi <= rsi_max:
        score += 10
        reasons.append(f"RSI masih ok ({last_rsi:.0f})")
    else:
        score += 5
        reasons.append(f"RSI ({last_rsi:.0f})")

    # MA (max 10)
    if above_ma:
        ma_gap = pct_change(last_close, last_ma)
        score += 10 if ma_gap >= 1 else 7
        reasons.append("Harga di atas MA")
    else:
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
