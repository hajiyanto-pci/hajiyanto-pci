"""Logika screening multi-faktor untuk potensi kenaikan harga."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from screener.indicators import (
    bandar_flow_score,
    bollinger,
    is_accumulating,
    macd,
    pct_change,
    resistance_level,
    rsi,
    sma,
    stochastic,
    suggest_sl_tp,
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
    stoch_k: float
    stoch_d: float
    cmf: float
    mfi: float
    macd_hist: float
    ma: float
    above_ma: bool
    accumulating: bool
    breakout: bool
    volume_ok: bool
    stoch_ok: bool
    money_flow_ok: bool
    macd_ok: bool
    score: float
    factor_scores: dict[str, float]
    reasons: list[str]
    entry: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    risk_pct: float = 0.0
    tp1_pct: float = 0.0
    tp2_pct: float = 0.0
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
    """Parse tanggal natural/ISO menjadi date Jakarta. Lihat screener.dates."""
    from screener.dates import parse_natural_date

    if value is None or str(value).strip() == "":
        return None
    return parse_natural_date(value, now=now)


def slice_as_of(df: pd.DataFrame, as_of: datetime.date | None) -> pd.DataFrame:
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
    require_stoch = bool(cfg.get("require_stoch", False))
    require_money_flow = bool(cfg.get("require_money_flow", True))
    stoch_k_period = int(cfg.get("stoch_k_period", 14))
    stoch_d_period = int(cfg.get("stoch_d_period", 3))
    stoch_max = float(cfg.get("stoch_max", 85))

    if mode in {"midday", "open"} and as_of is None:
        if mode == "open":
            vol_min = float(cfg.get("open_volume_spike_min", max(vol_min, 1.8)))
            min_score = float(cfg.get("open_min_score", max(min_score - 5, 55)))
        else:
            vol_min = float(cfg.get("midday_volume_spike_min", max(vol_min, 2.0)))
            min_score = float(cfg.get("midday_min_score", max(min_score, 70)))

    work = _prepare_frame(df, mode, now=now, as_of=as_of)
    need = max(vol_days, res_lookback, rsi_period, ma_period, accum_lookback, 35) + 2
    if work is None or len(work) < need:
        return None

    close = work["Close"].astype(float)
    high = work["High"].astype(float)
    low = work["Low"].astype(float)
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
    if mode in {"midday", "open"} and as_of is None:
        progress = session_progress(now)
        # Open (09:10) masih sangat awal → floor lebih rendah
        floor = 0.12 if mode == "open" else 0.25
        progress = max(progress, floor)
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

    k_series, d_series = stochastic(
        high, low, close, k_period=stoch_k_period, d_period=stoch_d_period
    )
    last_k = float(k_series.iloc[-1]) if np.isfinite(k_series.iloc[-1]) else 50.0
    last_d = float(d_series.iloc[-1]) if np.isfinite(d_series.iloc[-1]) else 50.0
    prev_k = float(k_series.iloc[-2]) if len(k_series) > 1 and np.isfinite(k_series.iloc[-2]) else last_k
    prev_d = float(d_series.iloc[-2]) if len(d_series) > 1 and np.isfinite(d_series.iloc[-2]) else last_d
    stoch_cross_up = prev_k <= prev_d and last_k > last_d
    stoch_ok = last_k <= stoch_max and (stoch_cross_up or 20 <= last_k <= 80)

    macd_line, macd_sig, macd_hist = macd(close)
    last_hist = (
        float(macd_hist.iloc[-1]) if np.isfinite(macd_hist.iloc[-1]) else 0.0
    )
    prev_hist = (
        float(macd_hist.iloc[-2])
        if len(macd_hist) > 1 and np.isfinite(macd_hist.iloc[-2])
        else last_hist
    )
    macd_ok = last_hist > 0 or last_hist > prev_hist

    money_ok, money_pts, money_note = bandar_flow_score(high, low, close, volume)
    # Ambil CMF/MFI terakhir untuk ditampilkan
    from screener.indicators import chaikin_money_flow, money_flow_index

    cmf_v = float(chaikin_money_flow(high, low, close, volume).iloc[-1] or 0)
    if not np.isfinite(cmf_v):
        cmf_v = 0.0
    mfi_v = float(money_flow_index(high, low, close, volume).iloc[-1] or 50)
    if not np.isfinite(mfi_v):
        mfi_v = 50.0

    upper, mid_bb, _lower = bollinger(close)
    last_upper = float(upper.iloc[-1]) if np.isfinite(upper.iloc[-1]) else last_close
    bb_break = last_close >= last_upper * 0.995

    accumulating, accum_note = is_accumulating(close, volume, lookback=accum_lookback)
    volume_ok = vol_ratio >= vol_min

    checklist = {
        "volume": volume_ok,
        "above_ma": above_ma,
        "accumulation": accumulating,
        "breakout": is_breakout,
        "stochastic": stoch_ok,
        "money_flow": money_ok,
        "macd": macd_ok,
    }

    if not volume_ok:
        return None
    if not is_breakout:
        return None
    if require_above_ma and not above_ma:
        return None
    if require_accumulation and not accumulating:
        return None
    if require_stoch and not stoch_ok:
        return None
    if require_money_flow and not money_ok:
        return None
    if last_rsi > rsi_max:
        return None

    score, factor_scores, reasons = _score_multifactor(
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
        last_k=last_k,
        last_d=last_d,
        stoch_cross_up=stoch_cross_up,
        stoch_ok=stoch_ok,
        money_pts=money_pts,
        money_note=money_note,
        macd_ok=macd_ok,
        last_hist=last_hist,
        bb_break=bb_break,
    )

    if as_of is not None:
        bar_day = _bar_date(work.index[-1])
        reasons.insert(0, f"Analisa as-of {as_of.isoformat()} (bar {bar_day.isoformat()})")
    elif mode == "morning":
        reasons.insert(0, "Watchlist dari breakout H-1 (siap pantau di open)")
    elif mode == "open":
        reasons.insert(0, "Early open 09:10 (volume awal, belum final)")
        if projected_note:
            reasons.insert(1, projected_note)
        score = max(0.0, score - 8)
    elif mode == "midday":
        reasons.insert(0, "Break sesi 1 / midday (volume berjalan, belum final)")
        if projected_note:
            reasons.insert(1, projected_note)
        score = max(0.0, score - 5)
    else:
        reasons.insert(0, "Sinyal EOD confirmed (multi-faktor)")

    if score < min_score:
        return None

    levels = suggest_sl_tp(
        last_close,
        high,
        low,
        close,
        atr_period=int(cfg.get("atr_period", 14)),
        sl_atr_mult=float(cfg.get("sl_atr_mult", 1.5)),
        tp1_rr=float(cfg.get("tp1_rr", 1.5)),
        tp2_rr=float(cfg.get("tp2_rr", 2.5)),
    )
    reasons.append(
        f"SL {levels['sl']:,.0f} (-{levels['risk_pct']:.1f}%) | "
        f"TP1 {levels['tp1']:,.0f} (+{levels['tp1_pct']:.1f}%) | "
        f"TP2 {levels['tp2']:,.0f} (+{levels['tp2_pct']:.1f}%)"
    )

    return Signal(
        symbol=from_yahoo_symbol(yahoo_symbol),
        price=round(last_close, 2),
        volume=round(last_vol, 0),
        volume_ratio=round(vol_ratio, 2),
        resistance=round(resist, 2),
        breakout_pct=round(breakout_pct, 2),
        rsi=round(last_rsi, 1),
        stoch_k=round(last_k, 1),
        stoch_d=round(last_d, 1),
        cmf=round(cmf_v, 3),
        mfi=round(mfi_v, 1),
        macd_hist=round(last_hist, 4),
        ma=round(last_ma, 2),
        above_ma=above_ma,
        accumulating=accumulating,
        breakout=is_breakout,
        volume_ok=volume_ok,
        stoch_ok=stoch_ok,
        money_flow_ok=money_ok,
        macd_ok=macd_ok,
        score=round(score, 1),
        factor_scores={k: round(v, 1) for k, v in factor_scores.items()},
        reasons=reasons,
        entry=levels["entry"],
        sl=levels["sl"],
        tp1=levels["tp1"],
        tp2=levels["tp2"],
        risk_pct=levels["risk_pct"],
        tp1_pct=levels["tp1_pct"],
        tp2_pct=levels["tp2_pct"],
        checklist=checklist,
        mode=mode,
    )


def _score_multifactor(
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
    last_k: float,
    last_d: float,
    stoch_cross_up: bool,
    stoch_ok: bool,
    money_pts: float,
    money_note: str,
    macd_ok: bool,
    last_hist: float,
    bb_break: bool,
) -> tuple[float, dict[str, float], list[str]]:
    """Formula skor 0-100 multi-faktor.

    Bobot default:
      Volume 20 | Breakout 18 | Money-flow/bandar 15 | Akumulasi OBV 12
      Stochastic 12 | MACD 8 | RSI 8 | MA 7
    """
    reasons: list[str] = []
    factors: dict[str, float] = {}

    # Volume (20)
    if vol_ratio >= vol_min * 3:
        factors["volume"] = 20
        reasons.append(f"Volume sangat tinggi ({vol_ratio:.1f}x)")
    elif vol_ratio >= vol_min * 2:
        factors["volume"] = 16
        reasons.append(f"Volume tinggi ({vol_ratio:.1f}x)")
    else:
        factors["volume"] = 11
        reasons.append(f"Volume di atas rata-rata ({vol_ratio:.1f}x)")

    # Breakout (18)
    if breakout_pct >= 3:
        factors["breakout"] = 18
        reasons.append(f"Break resistance kuat (+{breakout_pct:.1f}%)")
    elif breakout_pct >= 1:
        factors["breakout"] = 14
        reasons.append(f"Break resistance (+{breakout_pct:.1f}%)")
    else:
        factors["breakout"] = 10
        reasons.append(f"Break resistance tipis (+{breakout_pct:.1f}%)")
    if bb_break:
        factors["breakout"] = min(18.0, factors["breakout"] + 2)
        reasons.append("Dekat/tembus Bollinger upper")

    # Money flow / proksi bandar (15)
    factors["money_flow"] = float(money_pts)
    reasons.append(money_note)

    # Akumulasi OBV (12)
    if accumulating:
        factors["accumulation"] = 12
        reasons.append(accum_note)
    else:
        factors["accumulation"] = 0
        reasons.append(accum_note)

    # Stochastic (12)
    if stoch_cross_up and last_k < 80:
        factors["stochastic"] = 12
        reasons.append(f"Stoch golden-cross (%K {last_k:.0f} > %D {last_d:.0f})")
    elif 20 <= last_k <= 70 and last_k >= last_d:
        factors["stochastic"] = 9
        reasons.append(f"Stoch bullish (%K {last_k:.0f})")
    elif stoch_ok:
        factors["stochastic"] = 5
        reasons.append(f"Stoch ok (%K {last_k:.0f})")
    else:
        factors["stochastic"] = 0
        reasons.append(f"Stoch lemah/overbought (%K {last_k:.0f})")

    # MACD (8)
    if macd_ok and last_hist > 0:
        factors["macd"] = 8
        reasons.append("MACD histogram positif")
    elif macd_ok:
        factors["macd"] = 5
        reasons.append("MACD membaik")
    else:
        factors["macd"] = 0
        reasons.append("MACD belum mendukung")

    # RSI (8)
    if 50 <= last_rsi <= 65:
        factors["rsi"] = 8
        reasons.append(f"RSI sehat ({last_rsi:.0f})")
    elif 45 <= last_rsi < 50 or 65 < last_rsi <= rsi_max:
        factors["rsi"] = 5
        reasons.append(f"RSI masih ok ({last_rsi:.0f})")
    else:
        factors["rsi"] = 2
        reasons.append(f"RSI ({last_rsi:.0f})")

    # MA (7)
    if above_ma:
        ma_gap = pct_change(last_close, last_ma)
        factors["ma"] = 7 if ma_gap >= 1 else 5
        reasons.append("Harga di atas MA")
    else:
        factors["ma"] = 0
        reasons.append("Harga di bawah MA")

    score = float(sum(factors.values()))
    return min(score, 100.0), factors, reasons


def evaluate_stoch_oversold(
    yahoo_symbol: str,
    df: pd.DataFrame,
    cfg: dict,
    *,
    now: datetime | None = None,
) -> Signal | None:
    """Screen saham Stochastic oversold (hari ini / lookback minggu)."""
    mode = str(cfg.get("mode", "eod")).lower()
    as_of = cfg.get("as_of")
    vol_days = int(cfg.get("volume_avg_days", 20))
    min_avg_vol = float(cfg.get("min_avg_volume", 500_000))
    min_price = float(cfg.get("min_price", 50))
    stoch_k_period = int(cfg.get("stoch_k_period", 14))
    stoch_d_period = int(cfg.get("stoch_d_period", 3))
    oversold_max = float(cfg.get("stoch_oversold_max", 20))
    lookback = max(1, int(cfg.get("stoch_oversold_lookback", 1)))
    rsi_period = int(cfg.get("rsi_period", 14))
    ma_period = int(cfg.get("ma_period", 20))
    min_score = float(cfg.get("stoch_oversold_min_score", 45))

    work = _prepare_frame(df, mode, now=now, as_of=as_of)
    need = max(vol_days, stoch_k_period, ma_period, lookback, 35) + 2
    if work is None or len(work) < need:
        return None

    close = work["Close"].astype(float)
    high = work["High"].astype(float)
    low = work["Low"].astype(float)
    volume = work["Volume"].astype(float)

    last_close = float(close.iloc[-1])
    last_vol = float(volume.iloc[-1])
    if not np.isfinite(last_close) or last_close < min_price:
        return None

    avg_vol = float(volume.iloc[-(vol_days + 1) : -1].mean())
    if not np.isfinite(avg_vol) or avg_vol < min_avg_vol:
        return None
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0

    k_series, d_series = stochastic(
        high, low, close, k_period=stoch_k_period, d_period=stoch_d_period
    )
    last_k = float(k_series.iloc[-1]) if np.isfinite(k_series.iloc[-1]) else 50.0
    last_d = float(d_series.iloc[-1]) if np.isfinite(d_series.iloc[-1]) else 50.0
    prev_k = float(k_series.iloc[-2]) if len(k_series) > 1 and np.isfinite(k_series.iloc[-2]) else last_k
    prev_d = float(d_series.iloc[-2]) if len(d_series) > 1 and np.isfinite(d_series.iloc[-2]) else last_d
    stoch_cross_up = prev_k <= prev_d and last_k > last_d

    window_k = k_series.iloc[-lookback:].astype(float)
    window_k = window_k[np.isfinite(window_k)]
    if window_k.empty:
        return None
    min_k = float(window_k.min())
    currently_oversold = last_k <= oversold_max
    was_oversold = min_k <= oversold_max
    if not was_oversold:
        return None

    rsi_series = rsi(close, rsi_period)
    last_rsi = float(rsi_series.iloc[-1]) if np.isfinite(rsi_series.iloc[-1]) else 50.0
    ma_series = sma(close, ma_period)
    last_ma = float(ma_series.iloc[-1]) if np.isfinite(ma_series.iloc[-1]) else last_close
    above_ma = last_close > last_ma

    money_ok, money_pts, money_note = bandar_flow_score(high, low, close, volume)
    from screener.indicators import chaikin_money_flow, money_flow_index

    cmf_v = float(chaikin_money_flow(high, low, close, volume).iloc[-1] or 0)
    if not np.isfinite(cmf_v):
        cmf_v = 0.0
    mfi_v = float(money_flow_index(high, low, close, volume).iloc[-1] or 50)
    if not np.isfinite(mfi_v):
        mfi_v = 50.0

    accumulating, accum_note = is_accumulating(close, volume, lookback=10)
    resist = resistance_level(high, int(cfg.get("resistance_lookback", 20))) or last_close
    breakout_pct = pct_change(last_close, resist) if resist else 0.0
    is_breakout = last_close >= resist if resist else False

    # Skor khusus oversold (bukan formula breakout)
    score = 0.0
    reasons: list[str] = []
    factors: dict[str, float] = {}

    # Semakin dalam oversold → skor lebih tinggi
    depth = max(0.0, oversold_max - min(last_k if currently_oversold else min_k, oversold_max))
    stoch_pts = 35 + min(25.0, depth * 1.5)
    factors["stochastic"] = stoch_pts
    if currently_oversold:
        reasons.append(f"Stoch oversold sekarang (%K {last_k:.0f} / %D {last_d:.0f})")
    else:
        reasons.append(
            f"Stoch pernah oversold {lookback}d terakhir "
            f"(min %K {min_k:.0f}; sekarang {last_k:.0f})"
        )
        score -= 8  # sedikit penalti jika sudah naik dari oversold

    if stoch_cross_up and last_k <= oversold_max + 10:
        factors["stoch_turn"] = 15
        reasons.append("Stoch mulai putar naik (golden cross di zona rendah)")
    elif last_k > last_d and last_k <= oversold_max + 5:
        factors["stoch_turn"] = 8
        reasons.append("Stoch %K di atas %D di zona oversold")
    else:
        factors["stoch_turn"] = 0

    if last_rsi <= 30:
        factors["rsi"] = 12
        reasons.append(f"RSI juga oversold ({last_rsi:.0f})")
    elif last_rsi <= 40:
        factors["rsi"] = 8
        reasons.append(f"RSI rendah ({last_rsi:.0f})")
    else:
        factors["rsi"] = 3
        reasons.append(f"RSI {last_rsi:.0f}")

    if vol_ratio >= 1.5:
        factors["volume"] = 12
        reasons.append(f"Volume aktif ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.0:
        factors["volume"] = 7
        reasons.append(f"Volume normal ({vol_ratio:.1f}x)")
    else:
        factors["volume"] = 3
        reasons.append(f"Volume tipis ({vol_ratio:.1f}x)")

    if accumulating:
        factors["accumulation"] = 10
        reasons.append(accum_note)
    else:
        factors["accumulation"] = 0

    factors["money_flow"] = min(10.0, float(money_pts) * 0.6)
    reasons.append(money_note)

    if above_ma:
        factors["ma"] = 5
        reasons.append("Harga di atas MA (tren masih relatif kuat)")
    else:
        factors["ma"] = 2
        reasons.append("Harga di bawah MA (potensi mean-reversion)")

    score += float(sum(factors.values()))
    score = max(0.0, min(100.0, score))

    window_label = "hari ini" if lookback <= 1 else f"{lookback} hari perdagangan"
    reasons.insert(0, f"Filter Stochastic oversold ({window_label}, ambang %K ≤ {oversold_max:.0f})")
    if as_of is not None:
        bar_day = _bar_date(work.index[-1])
        reasons.insert(1, f"Analisa as-of {as_of.isoformat()} (bar {bar_day.isoformat()})")

    if score < min_score:
        return None

    levels = suggest_sl_tp(
        last_close,
        high,
        low,
        close,
        atr_period=int(cfg.get("atr_period", 14)),
        sl_atr_mult=float(cfg.get("sl_atr_mult", 1.5)),
        tp1_rr=float(cfg.get("tp1_rr", 1.5)),
        tp2_rr=float(cfg.get("tp2_rr", 2.5)),
    )
    reasons.append(
        f"SL {levels['sl']:,.0f} (-{levels['risk_pct']:.1f}%) | "
        f"TP1 {levels['tp1']:,.0f} (+{levels['tp1_pct']:.1f}%) | "
        f"TP2 {levels['tp2']:,.0f} (+{levels['tp2_pct']:.1f}%)"
    )

    checklist = {
        "volume": vol_ratio >= 1.0,
        "above_ma": above_ma,
        "accumulation": accumulating,
        "breakout": is_breakout,
        "stochastic": currently_oversold or was_oversold,
        "money_flow": money_ok,
        "macd": False,
        "stoch_oversold": currently_oversold or was_oversold,
    }

    return Signal(
        symbol=from_yahoo_symbol(yahoo_symbol),
        price=round(last_close, 2),
        volume=round(last_vol, 0),
        volume_ratio=round(vol_ratio, 2),
        resistance=round(float(resist), 2),
        breakout_pct=round(breakout_pct, 2),
        rsi=round(last_rsi, 1),
        stoch_k=round(last_k, 1),
        stoch_d=round(last_d, 1),
        cmf=round(cmf_v, 3),
        mfi=round(mfi_v, 1),
        macd_hist=0.0,
        ma=round(last_ma, 2),
        above_ma=above_ma,
        accumulating=accumulating,
        breakout=is_breakout,
        volume_ok=vol_ratio >= 1.0,
        stoch_ok=currently_oversold or was_oversold,
        money_flow_ok=money_ok,
        macd_ok=False,
        score=round(score, 1),
        factor_scores={k: round(v, 1) for k, v in factors.items()},
        reasons=reasons,
        entry=levels["entry"],
        sl=levels["sl"],
        tp1=levels["tp1"],
        tp2=levels["tp2"],
        risk_pct=levels["risk_pct"],
        tp1_pct=levels["tp1_pct"],
        tp2_pct=levels["tp2_pct"],
        checklist=checklist,
        mode=mode,
    )


def screen_all(
    histories: dict[str, pd.DataFrame],
    cfg: dict,
    *,
    now: datetime | None = None,
) -> list[Signal]:
    from screener.tech_screen import evaluate_for_screen_type

    signals: list[Signal] = []
    for sym, df in histories.items():
        sig = evaluate_for_screen_type(sym, df, cfg, now=now)
        if sig is not None:
            signals.append(sig)
    signals.sort(key=lambda s: s.score, reverse=True)
    return signals
