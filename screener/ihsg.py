"""IHSG outlook: technicals + macro + news."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf

from screener.indicators import rsi, sma
from screener.macro import fetch_macro_snapshot, format_macro_block, macro_bias_score
from screener.news import fetch_ihsg_headlines, format_news_block, news_bias_score


IHSG_SYMBOL = "^JKSE"


@dataclass
class IhsgOutlook:
    as_of: str
    last: float
    change_pct: float
    above_ma20: bool
    above_ma50: bool
    rsi: float | None
    decision: str  # BULLISH / NEUTRAL / BEARISH
    score: int
    technical_note: str
    macro_block: str
    news_block: str
    summary: str


def _download_ihsg(period: str = "6mo") -> pd.DataFrame:
    raw = yf.download(
        IHSG_SYMBOL,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.rename(columns=str.title)
    need = ["Open", "High", "Low", "Close", "Volume"]
    for col in need:
        if col not in df.columns:
            df[col] = 0.0
    return df[need].dropna(subset=["Close"])


def analyze_ihsg() -> IhsgOutlook | None:
    df = _download_ihsg()
    if df.empty or len(df) < 30:
        return None

    close = df["Close"].astype(float)
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    chg = (last - prev) / prev * 100.0 if prev else 0.0
    as_of = str(df.index[-1].date())

    ma20_s = sma(close, 20)
    ma50_s = sma(close, 50)
    rsi_s = rsi(close, 14)
    ma20 = float(ma20_s.iloc[-1]) if pd.notna(ma20_s.iloc[-1]) else None
    ma50 = float(ma50_s.iloc[-1]) if pd.notna(ma50_s.iloc[-1]) else None
    rsi_v = float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else None

    above_ma20 = bool(ma20 is not None and last >= ma20)
    above_ma50 = bool(ma50 is not None and last >= ma50)

    tech_score = 0
    notes: list[str] = []
    if above_ma20:
        tech_score += 1
        notes.append("di atas MA20 (tren jangka pendek positif)")
    else:
        tech_score -= 1
        notes.append("di bawah MA20 (tren jangka pendek lemah)")
    if above_ma50:
        tech_score += 1
        notes.append("di atas MA50 (tren menengah positif)")
    else:
        tech_score -= 1
        notes.append("di bawah MA50 (tren menengah lemah)")
    if rsi_v is not None:
        if rsi_v >= 70:
            tech_score -= 1
            notes.append(f"RSI {rsi_v:.0f} overbought — risiko koreksi")
        elif rsi_v <= 30:
            tech_score += 1
            notes.append(f"RSI {rsi_v:.0f} oversold — potensi rebound")
        elif rsi_v >= 55:
            tech_score += 1
            notes.append(f"RSI {rsi_v:.0f} mendukung momentum naik")
        elif rsi_v <= 45:
            tech_score -= 1
            notes.append(f"RSI {rsi_v:.0f} momentum lemah")
        else:
            notes.append(f"RSI {rsi_v:.0f} netral")

    if chg > 0.3:
        tech_score += 1
        notes.append(f"sesi terakhir +{chg:.2f}%")
    elif chg < -0.3:
        tech_score -= 1
        notes.append(f"sesi terakhir {chg:.2f}%")

    macro_points = fetch_macro_snapshot()
    headlines = fetch_ihsg_headlines()
    m_score = macro_bias_score(macro_points)
    n_score = news_bias_score(headlines)

    # Weight: technical 2x, macro 1x, news 1x (capped)
    total = tech_score * 2 + max(-3, min(3, m_score)) + max(-2, min(2, n_score))

    if total >= 4:
        decision = "BULLISH"
        summary = (
            "Potensi IHSG hari ini / ke depan cenderung menguat, "
            "didukung teknikal dan konteks makro/berita."
        )
    elif total <= -4:
        decision = "BEARISH"
        summary = (
            "Potensi IHSG cenderung terkoreksi atau melemah; "
            "waspadai tekanan makro/berita dan tren teknikal."
        )
    else:
        decision = "NEUTRAL"
        summary = (
            "IHSG cenderung sideways / selektif; "
            "tunggu konfirmasi arah dari makro dan volume asing."
        )

    return IhsgOutlook(
        as_of=as_of,
        last=last,
        change_pct=chg,
        above_ma20=above_ma20,
        above_ma50=above_ma50,
        rsi=rsi_v,
        decision=decision,
        score=total,
        technical_note="; ".join(notes),
        macro_block=format_macro_block(macro_points),
        news_block=format_news_block(headlines),
        summary=summary,
    )


def format_ihsg_report(outlook: IhsgOutlook) -> str:
    sign = "+" if outlook.change_pct >= 0 else ""
    rsi_txt = f"{outlook.rsi:.0f}" if outlook.rsi is not None else "n/a"
    lines = [
        f"📊 IHSG outlook (as of {outlook.as_of})",
        f"IHSG: {outlook.last:,.2f} ({sign}{outlook.change_pct:.2f}%)",
        f"Keputusan: {outlook.decision} (skor {outlook.score})",
        "",
        f"Teknikal: {outlook.technical_note}",
        f"MA20: {'di atas' if outlook.above_ma20 else 'di bawah'} | "
        f"MA50: {'di atas' if outlook.above_ma50 else 'di bawah'} | RSI: {rsi_txt}",
        "",
        outlook.macro_block,
        "",
        outlook.news_block,
        "",
        f"Ringkasan: {outlook.summary}",
        "",
        "Catatan: ini ringkasan heuristik (Yahoo + headline), bukan saran investasi.",
    ]
    return "\n".join(lines)


def analyze_ihsg_dict() -> dict[str, Any] | None:
    o = analyze_ihsg()
    if o is None:
        return None
    return {
        "as_of": o.as_of,
        "last": o.last,
        "change_pct": o.change_pct,
        "decision": o.decision,
        "score": o.score,
        "summary": o.summary,
        "report": format_ihsg_report(o),
    }
