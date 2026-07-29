"""Engine screening multi-preset (bandar, stoch cross, oversold, dll)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from screener.indicators import (
    bandar_flow_score,
    chaikin_money_flow,
    is_accumulating,
    macd,
    money_flow_index,
    pct_change,
    resistance_level,
    rsi,
    sma,
    stochastic,
    suggest_sl_tp,
)
from screener.presets import normalize_preset_key, preset_title
from screener.signals import Signal, _bar_date, _prepare_frame
from screener.universe import from_yahoo_symbol


@dataclass
class FeatureSnap:
    close: float
    volume: float
    vol_ratio: float
    last_k: float
    last_d: float
    prev_k: float
    prev_d: float
    stoch_cross_up: bool
    stoch_cross_recent: bool
    min_k: float
    last_rsi: float
    last_ma: float
    above_ma: bool
    cmf: float
    mfi: float
    money_ok: bool
    money_pts: float
    money_note: str
    accumulating: bool
    accum_note: str
    resistance: float
    breakout: bool
    breakout_pct: float
    macd_hist: float
    prev_macd_hist: float
    macd_turn_up: bool
    work: pd.DataFrame


def _compute_features(
    df: pd.DataFrame,
    cfg: dict,
    *,
    now: datetime | None = None,
) -> FeatureSnap | None:
    mode = str(cfg.get("mode", "eod")).lower()
    as_of = cfg.get("as_of")
    vol_days = int(cfg.get("volume_avg_days", 20))
    min_avg_vol = float(cfg.get("min_avg_volume", 500_000))
    min_price = float(cfg.get("min_price", 50))
    stoch_k_period = int(cfg.get("stoch_k_period", 14))
    stoch_d_period = int(cfg.get("stoch_d_period", 3))
    lookback = max(1, int(cfg.get("stoch_oversold_lookback", cfg.get("tech_lookback", 1))))
    rsi_period = int(cfg.get("rsi_period", 14))
    ma_period = int(cfg.get("ma_period", 20))
    res_lookback = int(cfg.get("resistance_lookback", 20))

    work = _prepare_frame(df, mode, now=now, as_of=as_of)
    need = max(vol_days, stoch_k_period, ma_period, lookback, 35) + 2
    if work is None or len(work) < need:
        return None

    close_s = work["Close"].astype(float)
    high = work["High"].astype(float)
    low = work["Low"].astype(float)
    volume = work["Volume"].astype(float)

    last_close = float(close_s.iloc[-1])
    last_vol = float(volume.iloc[-1])
    if not np.isfinite(last_close) or last_close < min_price:
        return None

    avg_vol = float(volume.iloc[-(vol_days + 1) : -1].mean())
    if not np.isfinite(avg_vol) or avg_vol < min_avg_vol:
        return None
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0

    k_series, d_series = stochastic(
        high, low, close_s, k_period=stoch_k_period, d_period=stoch_d_period
    )
    last_k = float(k_series.iloc[-1]) if np.isfinite(k_series.iloc[-1]) else 50.0
    last_d = float(d_series.iloc[-1]) if np.isfinite(d_series.iloc[-1]) else 50.0
    prev_k = float(k_series.iloc[-2]) if len(k_series) > 1 and np.isfinite(k_series.iloc[-2]) else last_k
    prev_d = float(d_series.iloc[-2]) if len(d_series) > 1 and np.isfinite(d_series.iloc[-2]) else last_d
    stoch_cross_up = prev_k <= prev_d and last_k > last_d

    # Cross ke atas dalam lookback (untuk "minggu ini")
    stoch_cross_recent = stoch_cross_up
    if lookback > 1 and len(k_series) >= lookback + 1:
        for i in range(-(lookback), 0):
            kk = float(k_series.iloc[i]) if np.isfinite(k_series.iloc[i]) else None
            dd = float(d_series.iloc[i]) if np.isfinite(d_series.iloc[i]) else None
            pk = float(k_series.iloc[i - 1]) if np.isfinite(k_series.iloc[i - 1]) else None
            pd_ = float(d_series.iloc[i - 1]) if np.isfinite(d_series.iloc[i - 1]) else None
            if None in (kk, dd, pk, pd_):
                continue
            if pk <= pd_ and kk > dd:
                stoch_cross_recent = True
                break

    window_k = k_series.iloc[-lookback:].astype(float)
    window_k = window_k[np.isfinite(window_k)]
    min_k = float(window_k.min()) if not window_k.empty else last_k

    rsi_series = rsi(close_s, rsi_period)
    last_rsi = float(rsi_series.iloc[-1]) if np.isfinite(rsi_series.iloc[-1]) else 50.0
    ma_series = sma(close_s, ma_period)
    last_ma = float(ma_series.iloc[-1]) if np.isfinite(ma_series.iloc[-1]) else last_close
    above_ma = last_close > last_ma

    money_ok, money_pts, money_note = bandar_flow_score(high, low, close_s, volume)
    cmf_v = float(chaikin_money_flow(high, low, close_s, volume).iloc[-1] or 0)
    if not np.isfinite(cmf_v):
        cmf_v = 0.0
    mfi_v = float(money_flow_index(high, low, close_s, volume).iloc[-1] or 50)
    if not np.isfinite(mfi_v):
        mfi_v = 50.0

    accumulating, accum_note = is_accumulating(
        close_s, volume, lookback=int(cfg.get("accumulation_lookback", 10))
    )
    resist = resistance_level(high, res_lookback) or last_close
    breakout_pct = pct_change(last_close, resist) if resist else 0.0
    is_breakout = last_close >= float(resist)

    _line, _sig, macd_hist = macd(close_s)
    last_hist = float(macd_hist.iloc[-1]) if np.isfinite(macd_hist.iloc[-1]) else 0.0
    prev_hist = (
        float(macd_hist.iloc[-2])
        if len(macd_hist) > 1 and np.isfinite(macd_hist.iloc[-2])
        else last_hist
    )
    macd_turn_up = prev_hist <= 0 <= last_hist or (last_hist > prev_hist and last_hist > 0)

    return FeatureSnap(
        close=last_close,
        volume=last_vol,
        vol_ratio=vol_ratio,
        last_k=last_k,
        last_d=last_d,
        prev_k=prev_k,
        prev_d=prev_d,
        stoch_cross_up=stoch_cross_up,
        stoch_cross_recent=stoch_cross_recent,
        min_k=min_k,
        last_rsi=last_rsi,
        last_ma=last_ma,
        above_ma=above_ma,
        cmf=cmf_v,
        mfi=mfi_v,
        money_ok=money_ok,
        money_pts=money_pts,
        money_note=money_note,
        accumulating=accumulating,
        accum_note=accum_note,
        resistance=float(resist),
        breakout=is_breakout,
        breakout_pct=breakout_pct,
        macd_hist=last_hist,
        prev_macd_hist=prev_hist,
        macd_turn_up=macd_turn_up,
        work=work,
    )


def _score_common(f: FeatureSnap) -> tuple[dict[str, float], list[str]]:
    factors: dict[str, float] = {}
    reasons: list[str] = []
    if f.vol_ratio >= 2:
        factors["volume"] = 12
        reasons.append(f"Volume tinggi ({f.vol_ratio:.1f}x)")
    elif f.vol_ratio >= 1.2:
        factors["volume"] = 7
        reasons.append(f"Volume aktif ({f.vol_ratio:.1f}x)")
    else:
        factors["volume"] = 3
        reasons.append(f"Volume {f.vol_ratio:.1f}x")

    if f.accumulating:
        factors["accumulation"] = 10
        reasons.append(f.accum_note)
    else:
        factors["accumulation"] = 0

    factors["money_flow"] = min(12.0, float(f.money_pts) * 0.7)
    reasons.append(f.money_note)

    if f.above_ma:
        factors["ma"] = 5
        reasons.append("Di atas MA")
    else:
        factors["ma"] = 2
        reasons.append("Di bawah MA")
    return factors, reasons


def _passes_and_score(preset: str, f: FeatureSnap, cfg: dict) -> tuple[bool, float, dict[str, float], list[str]]:
    oversold_max = float(cfg.get("stoch_oversold_max", 20))
    lookback = max(1, int(cfg.get("stoch_oversold_lookback", cfg.get("tech_lookback", 1))))
    vol_min = float(cfg.get("volume_spike_min", 1.5))
    factors, reasons = _score_common(f)
    score_bonus = 0.0
    ok = False
    title = preset_title(preset)

    if preset == "stoch_oversold":
        currently = f.last_k <= oversold_max
        was = f.min_k <= oversold_max
        ok = was
        depth = max(0.0, oversold_max - min(f.last_k if currently else f.min_k, oversold_max))
        factors["stochastic"] = 35 + min(25.0, depth * 1.5)
        if currently:
            reasons.insert(0, f"Stoch oversold (%K {f.last_k:.0f} / %D {f.last_d:.0f})")
        else:
            reasons.insert(
                0,
                f"Pernah oversold {lookback}d (min %K {f.min_k:.0f}; sekarang {f.last_k:.0f})",
            )
            score_bonus -= 8
        if f.stoch_cross_up and f.last_k <= oversold_max + 10:
            factors["stoch_turn"] = 15
            reasons.append("Stoch mulai cross ke atas di zona rendah")
        if f.last_rsi <= 35:
            factors["rsi"] = 10
            reasons.append(f"RSI rendah ({f.last_rsi:.0f})")

    elif preset == "stoch_cross":
        ok = f.stoch_cross_up or (lookback > 1 and f.stoch_cross_recent)
        factors["stochastic"] = 40 if f.last_k <= 40 else 28
        if f.stoch_cross_up:
            reasons.insert(
                0,
                f"Stoch cross ke atas (%K {f.last_k:.0f} > %D {f.last_d:.0f})",
            )
        else:
            reasons.insert(
                0,
                f"Stoch pernah cross ke atas dalam {lookback}d "
                f"(sekarang %K {f.last_k:.0f} / %D {f.last_d:.0f})",
            )
            score_bonus -= 5
        if f.last_k <= 30:
            factors["stoch_zone"] = 18
            reasons.append("Cross dari zona oversold (lebih menarik)")
        elif f.last_k <= 50:
            factors["stoch_zone"] = 10
            reasons.append("Cross dari zona menengah-bawah")
        else:
            factors["stoch_zone"] = 0
            reasons.append("Cross di zona tinggi — waspada")

    elif preset == "stoch_bullish":
        # Stochastic "lagi bagus / potensi naik":
        # - cross ke atas, ATAU
        # - %K > %D di zona sehat 20–80, ATAU
        # - rebound dari oversold (%K naik dari ≤25)
        healthy = f.last_k > f.last_d and 20 <= f.last_k <= 80
        rebound = f.min_k <= 25 and f.last_k > f.last_d and f.last_k <= 55
        ok = f.stoch_cross_up or f.stoch_cross_recent or healthy or rebound
        factors["stochastic"] = 0
        if f.stoch_cross_up:
            factors["stochastic"] += 35
            reasons.insert(
                0,
                f"Stoch bullish: cross ke atas (%K {f.last_k:.0f} > %D {f.last_d:.0f})",
            )
        elif healthy:
            factors["stochastic"] += 30
            reasons.insert(
                0,
                f"Stoch bullish: %K > %D di zona sehat ({f.last_k:.0f}/{f.last_d:.0f})",
            )
        elif rebound:
            factors["stochastic"] += 32
            reasons.insert(
                0,
                f"Stoch rebound dari oversold (min {f.min_k:.0f} → %K {f.last_k:.0f})",
            )
        elif f.stoch_cross_recent:
            factors["stochastic"] += 25
            reasons.insert(0, f"Stoch pernah cross naik {lookback}d terakhir")
        if 25 <= f.last_k <= 65:
            factors["stoch_zone"] = 12
            reasons.append("Zona Stochastic ideal untuk potensi lanjut naik")
        elif f.last_k < 20:
            factors["stoch_zone"] = 8
            reasons.append("Masih oversold — pantau konfirmasi cross")
        elif f.last_k > 80:
            factors["stoch_zone"] = 0
            reasons.append("Stoch tinggi — risiko jenuh beli")
            score_bonus -= 8
        if f.macd_turn_up:
            factors["macd_confirm"] = 8
            reasons.append("MACD mendukung")
        if f.vol_ratio >= 1.2:
            factors["vol_confirm"] = 6

    elif preset == "bandar":
        ok = f.money_ok and f.cmf >= 0.05
        factors["bandar"] = 40 + min(20.0, max(0.0, f.cmf) * 80)
        reasons.insert(0, f"Bandarmology proxy: CMF {f.cmf:.2f}, MFI {f.mfi:.0f}")
        if f.accumulating:
            factors["bandar_obv"] = 15
            reasons.append("Diperkuat akumulasi OBV")
        if f.vol_ratio >= 1.3:
            factors["bandar_vol"] = 10
            reasons.append("Volume mendukung aliran dana")

    elif preset == "accumulation":
        ok = f.accumulating
        factors["accumulation_main"] = 45
        reasons.insert(0, f.accum_note)
        if f.money_ok:
            factors["money_support"] = 15
            reasons.append("Money-flow ikut mendukung")
        if f.vol_ratio >= 1.2:
            factors["vol_support"] = 10

    elif preset == "volume":
        ok = f.vol_ratio >= vol_min
        factors["volume_main"] = 40 + min(25.0, (f.vol_ratio - vol_min) * 8)
        reasons.insert(0, f"Volume spike {f.vol_ratio:.1f}x (≥ {vol_min:.1f}x)")
        if f.breakout:
            factors["with_breakout"] = 12
            reasons.append("Disertai break resistance")
        if f.accumulating:
            factors["with_accum"] = 10

    elif preset == "rsi_oversold":
        rsi_max = float(cfg.get("rsi_oversold_max", 30))
        ok = f.last_rsi <= rsi_max
        depth = max(0.0, rsi_max - f.last_rsi)
        factors["rsi"] = 40 + min(25.0, depth * 2)
        reasons.insert(0, f"RSI oversold ({f.last_rsi:.0f} ≤ {rsi_max:.0f})")
        if f.last_k <= 25:
            factors["stoch_confirm"] = 12
            reasons.append(f"Stoch juga rendah (%K {f.last_k:.0f})")

    elif preset == "macd_turn":
        ok = f.macd_turn_up
        factors["macd"] = 40 if f.macd_hist > 0 else 28
        reasons.insert(
            0,
            f"MACD putar naik (hist {f.prev_macd_hist:.3f} → {f.macd_hist:.3f})",
        )
        if f.stoch_cross_up:
            factors["stoch_confirm"] = 12
            reasons.append("Diperkuat stoch cross ke atas")
        if f.above_ma:
            factors["ma_confirm"] = 8

    else:
        ok = False

    reasons.insert(0, f"Filter: {title}")
    score = float(sum(factors.values())) + score_bonus
    score = max(0.0, min(100.0, score))
    return ok, score, factors, reasons


def evaluate_tech_preset(
    yahoo_symbol: str,
    df: pd.DataFrame,
    cfg: dict,
    *,
    now: datetime | None = None,
) -> Signal | None:
    preset = normalize_preset_key(str(cfg.get("screen_type", "stoch_oversold")))
    if preset == "breakout":
        return None  # handled by evaluate_symbol

    f = _compute_features(df, cfg, now=now)
    if f is None:
        return None

    ok, score, factors, reasons = _passes_and_score(preset, f, cfg)
    if not ok:
        return None

    min_score = float(
        cfg.get(
            "tech_min_score",
            cfg.get("stoch_oversold_min_score", 35),
        )
    )
    as_of = cfg.get("as_of")
    if as_of is not None:
        bar_day = _bar_date(f.work.index[-1])
        reasons.insert(1, f"Analisa as-of {as_of.isoformat()} (bar {bar_day.isoformat()})")

    if score < min_score:
        return None

    close_s = f.work["Close"].astype(float)
    high = f.work["High"].astype(float)
    low = f.work["Low"].astype(float)
    levels = suggest_sl_tp(
        f.close,
        high,
        low,
        close_s,
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
        "volume": f.vol_ratio >= 1.0,
        "above_ma": f.above_ma,
        "accumulation": f.accumulating,
        "breakout": f.breakout,
        "stochastic": f.stoch_cross_up or f.last_k <= 20,
        "money_flow": f.money_ok,
        "macd": f.macd_turn_up,
        preset: True,
    }

    return Signal(
        symbol=from_yahoo_symbol(yahoo_symbol),
        price=round(f.close, 2),
        volume=round(f.volume, 0),
        volume_ratio=round(f.vol_ratio, 2),
        resistance=round(f.resistance, 2),
        breakout_pct=round(f.breakout_pct, 2),
        rsi=round(f.last_rsi, 1),
        stoch_k=round(f.last_k, 1),
        stoch_d=round(f.last_d, 1),
        cmf=round(f.cmf, 3),
        mfi=round(f.mfi, 1),
        macd_hist=round(f.macd_hist, 4),
        ma=round(f.last_ma, 2),
        above_ma=f.above_ma,
        accumulating=f.accumulating,
        breakout=f.breakout,
        volume_ok=f.vol_ratio >= 1.0,
        stoch_ok=f.stoch_cross_up or f.last_k <= 25,
        money_flow_ok=f.money_ok,
        macd_ok=f.macd_turn_up,
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
        mode=str(cfg.get("mode", "eod")),
    )


def evaluate_for_screen_type(
    yahoo_symbol: str,
    df: pd.DataFrame,
    cfg: dict,
    *,
    now: datetime | None = None,
) -> Signal | None:
    from screener.signals import evaluate_symbol

    preset = normalize_preset_key(str(cfg.get("screen_type", "breakout")))
    if preset == "breakout":
        return evaluate_symbol(yahoo_symbol, df, cfg, now=now)
    return evaluate_tech_preset(yahoo_symbol, df, {**cfg, "screen_type": preset}, now=now)
