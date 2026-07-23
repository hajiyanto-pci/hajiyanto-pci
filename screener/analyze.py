"""Analisa detail 1 saham + saran keputusan (untuk chat bot)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import yaml

from screener.data import fetch_history
from screener.indicators import (
    bandar_flow_score,
    is_accumulating,
    macd,
    pct_change,
    resistance_level,
    rsi,
    sma,
    stochastic,
    suggest_sl_tp,
)
from screener.signals import _prepare_frame, parse_as_of
from screener.universe import from_yahoo_symbol, to_yahoo_symbol


@dataclass
class StockReport:
    symbol: str
    price: float
    ma: float
    above_ma: bool
    volume_ratio: float
    resistance: float
    breakout: bool
    breakout_pct: float
    rsi: float
    stoch_k: float
    stoch_d: float
    cmf: float
    mfi: float
    macd_hist: float
    accumulating: bool
    score: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    risk_pct: float
    tp1_pct: float
    tp2_pct: float
    checklist: dict[str, bool] = field(default_factory=dict)
    decision: str = ""
    outlook: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "score": self.score,
            "decision": self.decision,
            "checklist": self.checklist,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
        }


def _soft_score(
    *,
    vol_ratio: float,
    breakout: bool,
    breakout_pct: float,
    above_ma: bool,
    accumulating: bool,
    stoch_k: float,
    stoch_d: float,
    money_ok: bool,
    money_pts: float,
    macd_hist: float,
    rsi_v: float,
) -> tuple[float, dict[str, bool], list[str]]:
    notes: list[str] = []
    checklist = {
        "volume": vol_ratio >= 1.5,
        "above_ma": above_ma,
        "accumulation": accumulating,
        "breakout": breakout,
        "stochastic": stoch_k <= 85 and (stoch_k >= stoch_d or 20 <= stoch_k <= 80),
        "money_flow": money_ok,
        "macd": macd_hist > 0,
    }
    score = 0.0

    if vol_ratio >= 3:
        score += 20
        notes.append(f"Volume sangat tinggi ({vol_ratio:.1f}x)")
    elif vol_ratio >= 2:
        score += 16
        notes.append(f"Volume tinggi ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.5:
        score += 11
        notes.append(f"Volume di atas rata-rata ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.0:
        score += 6
        notes.append(f"Volume normal ({vol_ratio:.1f}x)")
    else:
        notes.append(f"Volume lemah ({vol_ratio:.1f}x)")

    if breakout and breakout_pct >= 3:
        score += 18
        notes.append(f"Break resistance kuat (+{breakout_pct:.1f}%)")
    elif breakout and breakout_pct >= 1:
        score += 14
        notes.append(f"Break resistance (+{breakout_pct:.1f}%)")
    elif breakout:
        score += 10
        notes.append(f"Break tipis (+{breakout_pct:.1f}%)")
    else:
        notes.append(f"Belum break resistance (jarak {breakout_pct:.1f}%)")

    score += float(money_pts)
    if money_ok:
        notes.append("Money-flow/bandar-proxy mendukung")
    else:
        notes.append("Money-flow belum mendukung")

    if accumulating:
        score += 12
        notes.append("Akumulasi OBV terlihat")
    else:
        notes.append("Belum akumulasi OBV")

    if checklist["stochastic"]:
        score += 9 if stoch_k >= stoch_d else 5
        notes.append(f"Stochastic %K {stoch_k:.0f} / %D {stoch_d:.0f}")
    else:
        notes.append(f"Stochastic kurang ideal (%K {stoch_k:.0f})")

    if macd_hist > 0:
        score += 8
        notes.append("MACD histogram positif")
    else:
        notes.append("MACD belum positif")

    if 50 <= rsi_v <= 65:
        score += 8
        notes.append(f"RSI sehat ({rsi_v:.0f})")
    elif 40 <= rsi_v < 50 or 65 < rsi_v <= 75:
        score += 5
        notes.append(f"RSI ok ({rsi_v:.0f})")
    else:
        score += 2
        notes.append(f"RSI ({rsi_v:.0f})")

    if above_ma:
        score += 7
        notes.append("Harga di atas MA")
    else:
        notes.append("Harga di bawah MA")

    return min(score, 100.0), checklist, notes


def _decision(score: float, checklist: dict[str, bool], breakout_pct: float) -> tuple[str, str]:
    passed = sum(1 for v in checklist.values() if v)
    strong = (
        checklist.get("volume")
        and checklist.get("breakout")
        and checklist.get("above_ma")
        and checklist.get("accumulation")
    )
    if score >= 72 and strong:
        return (
            "BELI BERTAHAP",
            "Setup breakout + volume + akumulasi cukup kuat. "
            "Masuk bertahap dekat Entry, patuhi SL. Jangan FOMO jika sudah jauh di atas TP1.",
        )
    if score >= 62 and checklist.get("above_ma") and (
        checklist.get("breakout") or checklist.get("volume")
    ):
        return (
            "PANTAU / WAIT CONFIRM",
            "Ada potensi lanjut naik, tapi tunggu penutupan di atas resistance "
            "dengan volume tetap tinggi. Siapkan order jika break terkonsolidasi.",
        )
    if score >= 50 and checklist.get("above_ma"):
        return (
            "NETRAL / HOLD IDE",
            "Tren masih di atas MA, namun belum setup masuk ideal. "
            "Pantau volume & money-flow beberapa hari ke depan.",
        )
    if breakout_pct < -3 or not checklist.get("above_ma"):
        return (
            "HINDARI DULU",
            "Struktur belum mendukung (di bawah MA / jauh dari breakout). "
            "Lebih baik tunggu harga kembali ke area support/MA atau sinyal akumulasi baru.",
        )
    return (
        "TUNGGU SETUP",
        f"Baru {passed}/7 checklist lolos. Tunggu konfluensi volume + break + money-flow "
        "sebelum entry.",
    )


def analyze_stock(
    code: str,
    *,
    config_path: str = "config.yaml",
    as_of: str | None = None,
    history_days: int = 120,
) -> StockReport:
    symbol = code.strip().upper().replace(".JK", "")
    if not symbol:
        raise ValueError("Kode saham kosong")

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    yahoo = to_yahoo_symbol(symbol, "IDX")
    histories = fetch_history([symbol], history_days=history_days, market="IDX")
    if yahoo not in histories and f"{symbol}.JK" not in histories:
        # keys are yahoo symbols
        if not histories:
            raise ValueError(f"Data {symbol} tidak ditemukan di Yahoo Finance")
        yahoo = next(iter(histories.keys()))
    df = histories.get(yahoo)
    if df is None or df.empty:
        raise ValueError(f"Data {symbol} kosong / tidak tersedia")

    parsed = parse_as_of(as_of)
    work = _prepare_frame(df, "eod", as_of=parsed)
    if work is None or len(work) < 40:
        raise ValueError(f"Data historis {symbol} kurang untuk analisa")

    close = work["Close"].astype(float)
    high = work["High"].astype(float)
    low = work["Low"].astype(float)
    volume = work["Volume"].astype(float)

    last_close = float(close.iloc[-1])
    avg_vol = float(volume.iloc[-21:-1].mean())
    last_vol = float(volume.iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0

    resist = resistance_level(high, int(cfg.get("resistance_lookback", 20))) or last_close
    breakout = last_close >= resist
    breakout_pct = pct_change(last_close, resist)

    ma_period = int(cfg.get("ma_period", 20))
    last_ma = float(sma(close, ma_period).iloc[-1])
    above_ma = last_close > last_ma

    last_rsi = float(rsi(close, int(cfg.get("rsi_period", 14))).iloc[-1])
    k, d = stochastic(high, low, close)
    last_k = float(k.iloc[-1]) if np.isfinite(k.iloc[-1]) else 50.0
    last_d = float(d.iloc[-1]) if np.isfinite(d.iloc[-1]) else 50.0

    money_ok, money_pts, _money_note = bandar_flow_score(high, low, close, volume)
    from screener.indicators import chaikin_money_flow, money_flow_index

    cmf_v = float(chaikin_money_flow(high, low, close, volume).iloc[-1] or 0)
    if not np.isfinite(cmf_v):
        cmf_v = 0.0
    mfi_v = float(money_flow_index(high, low, close, volume).iloc[-1] or 50)
    if not np.isfinite(mfi_v):
        mfi_v = 50.0

    _, _, hist = macd(close)
    last_hist = float(hist.iloc[-1]) if np.isfinite(hist.iloc[-1]) else 0.0
    accumulating, _acc_note = is_accumulating(
        close, volume, lookback=int(cfg.get("accumulation_lookback", 10))
    )

    score, checklist, notes = _soft_score(
        vol_ratio=vol_ratio,
        breakout=breakout,
        breakout_pct=breakout_pct,
        above_ma=above_ma,
        accumulating=accumulating,
        stoch_k=last_k,
        stoch_d=last_d,
        money_ok=money_ok,
        money_pts=money_pts,
        macd_hist=last_hist,
        rsi_v=last_rsi,
    )
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
    decision, outlook = _decision(score, checklist, breakout_pct)

    return StockReport(
        symbol=from_yahoo_symbol(yahoo),
        price=round(last_close, 2),
        ma=round(last_ma, 2),
        above_ma=above_ma,
        volume_ratio=round(vol_ratio, 2),
        resistance=round(float(resist), 2),
        breakout=breakout,
        breakout_pct=round(breakout_pct, 2),
        rsi=round(last_rsi, 1),
        stoch_k=round(last_k, 1),
        stoch_d=round(last_d, 1),
        cmf=round(cmf_v, 3),
        mfi=round(mfi_v, 1),
        macd_hist=round(last_hist, 4),
        accumulating=accumulating,
        score=round(score, 1),
        entry=levels["entry"],
        sl=levels["sl"],
        tp1=levels["tp1"],
        tp2=levels["tp2"],
        risk_pct=levels["risk_pct"],
        tp1_pct=levels["tp1_pct"],
        tp2_pct=levels["tp2_pct"],
        checklist=checklist,
        decision=decision,
        outlook=outlook,
        notes=notes,
    )


def format_stock_report(r: StockReport) -> str:
    def mark(ok: bool) -> str:
        return "✅" if ok else "❌"

    c = r.checklist
    lines = [
        f"📊 Analisa {r.symbol}",
        f"Harga: {r.price:,.0f} | Skor: {r.score}/100",
        f"Keputusan: {r.decision}",
        "",
        "Checklist teknikal:",
        f"{mark(c.get('volume', False))} Volume {r.volume_ratio:.1f}x rata-rata",
        f"{mark(c.get('above_ma', False))} MA20 {r.ma:,.0f} ({'di atas' if r.above_ma else 'di bawah'})",
        f"{mark(c.get('accumulation', False))} Akumulasi OBV",
        f"{mark(c.get('breakout', False))} Break resistance {r.resistance:,.0f} ({r.breakout_pct:+.1f}%)",
        f"{mark(c.get('stochastic', False))} Stochastic %K {r.stoch_k:.0f} / %D {r.stoch_d:.0f}",
        f"{mark(c.get('money_flow', False))} Money-flow CMF {r.cmf:.2f} | MFI {r.mfi:.0f}",
        f"{mark(c.get('macd', False))} MACD hist {r.macd_hist:.4f}",
        f"RSI: {r.rsi:.0f}",
        "",
        "Saran level:",
        f"🎯 Entry ~{r.entry:,.0f}",
        f"🛑 SL {r.sl:,.0f} (-{r.risk_pct:.1f}%)",
        f"✅ TP1 {r.tp1:,.0f} (+{r.tp1_pct:.1f}%)",
        f"✅ TP2 {r.tp2:,.0f} (+{r.tp2_pct:.1f}%)",
        "",
        f"Saran ke depan: {r.outlook}",
    ]
    if r.notes:
        lines.append("")
        lines.append("Catatan:")
        for n in r.notes[:6]:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("Disclaimer: ini analisa teknikal otomatis, bukan rekomendasi investasi.")
    return "\n".join(lines)
