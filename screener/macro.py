"""Macro market snapshot (Yahoo Finance) for IHSG context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


# Symbol → human label + how move affects IHSG risk appetite (heuristic).
MACRO_SERIES: dict[str, dict[str, Any]] = {
    "USDIDR=X": {
        "label": "USD/IDR",
        "unit": "",
        # higher USDIDR = weaker Rupiah = usually risk-off for IHSG
        "ihsg_bias_if_up": -1,
    },
    "^GSPC": {
        "label": "S&P 500",
        "unit": "",
        "ihsg_bias_if_up": 1,
    },
    "^IXIC": {
        "label": "Nasdaq",
        "unit": "",
        "ihsg_bias_if_up": 1,
    },
    "CL=F": {
        "label": "Minyak (WTI)",
        "unit": " USD",
        "ihsg_bias_if_up": 0,  # mixed for Indonesia
    },
    "GC=F": {
        "label": "Emas",
        "unit": " USD",
        "ihsg_bias_if_up": -1,  # risk-off proxy
    },
    "^TNX": {
        "label": "US 10Y yield",
        "unit": "%",
        "ihsg_bias_if_up": -1,
    },
}


@dataclass
class MacroPoint:
    symbol: str
    label: str
    last: float
    change_pct: float
    bias: int  # -1 / 0 / +1 contribution toward IHSG risk-on
    note: str


def _last_two_closes(symbol: str, period: str = "10d") -> tuple[float, float] | None:
    try:
        raw = yf.download(
            symbol,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) < 2:
        return None
    return float(close.iloc[-2]), float(close.iloc[-1])


def fetch_macro_snapshot() -> list[MacroPoint]:
    out: list[MacroPoint] = []
    for symbol, meta in MACRO_SERIES.items():
        pair = _last_two_closes(symbol)
        if pair is None:
            continue
        prev, last = pair
        if prev == 0:
            continue
        chg = (last - prev) / prev * 100.0
        direction = 1 if chg > 0.05 else (-1 if chg < -0.05 else 0)
        bias = direction * int(meta["ihsg_bias_if_up"])
        if meta["ihsg_bias_if_up"] == 0:
            note = "dampak campuran ke IHSG"
        elif bias > 0:
            note = "mendukung risk-on IHSG"
        elif bias < 0:
            note = "menekan risk appetite IHSG"
        else:
            note = "netral"
        out.append(
            MacroPoint(
                symbol=symbol,
                label=str(meta["label"]),
                last=last,
                change_pct=chg,
                bias=bias,
                note=note,
            )
        )
    return out


def macro_bias_score(points: list[MacroPoint]) -> int:
    return sum(p.bias for p in points)


def format_macro_block(points: list[MacroPoint]) -> str:
    if not points:
        return "Makro: data tidak tersedia."
    lines = ["Makro (Yahoo Finance):"]
    for p in points:
        sign = "+" if p.change_pct >= 0 else ""
        lines.append(
            f"• {p.label}: {p.last:,.2f}{MACRO_SERIES[p.symbol]['unit']} "
            f"({sign}{p.change_pct:.2f}%) — {p.note}"
        )
    total = macro_bias_score(points)
    if total >= 2:
        tone = "Makro keseluruhan cenderung mendukung IHSG."
    elif total <= -2:
        tone = "Makro keseluruhan cenderung menekan IHSG."
    else:
        tone = "Makro keseluruhan campuran / netral."
    lines.append(tone)
    return "\n".join(lines)
