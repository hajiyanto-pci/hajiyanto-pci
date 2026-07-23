"""Ambil data harga dari Yahoo Finance."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd
import yfinance as yf

from screener.universe import to_yahoo_symbol

logger = logging.getLogger(__name__)


def fetch_history(
    symbols: Iterable[str],
    history_days: int = 90,
    market: str = "IDX",
) -> dict[str, pd.DataFrame]:
    yahoo_symbols = [to_yahoo_symbol(s, market) for s in symbols]
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=max(history_days + 30, 60))

    data = yf.download(
        tickers=yahoo_symbols,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    result: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return result

    if len(yahoo_symbols) == 1:
        sym = yahoo_symbols[0]
        df = _extract_ticker_frame(data, sym)
        df = _normalize_ohlcv(df)
        if not df.empty:
            result[sym] = df
        return result

    for sym in yahoo_symbols:
        try:
            df = _extract_ticker_frame(data, sym)
            df = _normalize_ohlcv(df)
            if df.empty or len(df) < 30:
                continue
            result[sym] = df
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gagal parse %s: %s", sym, exc)
    return result


def _extract_ticker_frame(data: pd.DataFrame, sym: str) -> pd.DataFrame:
    """Ambil frame 1 ticker dari hasil yfinance (MultiIndex / flat)."""
    if not isinstance(data.columns, pd.MultiIndex):
        return data.copy()

    level0 = data.columns.get_level_values(0)
    level1 = data.columns.get_level_values(1)

    # Bentuk: (TICKER, Open/High/...)
    if sym in level0:
        return data[sym].copy()

    # Bentuk: (Open/High/..., TICKER)
    if sym in level1:
        try:
            return data.xs(sym, axis=1, level=1).copy()
        except Exception:  # noqa: BLE001
            pass

    # Fallback: flatten names
    flat = data.copy()
    flat.columns = [
        c[1] if isinstance(c, tuple) and str(c[0]).endswith(".JK") else (
            c[0] if isinstance(c, tuple) else c
        )
        for c in data.columns
    ]
    return flat


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # Jika masih MultiIndex, ambil level harga
    if isinstance(df.columns, pd.MultiIndex):
        # prefer level yang berisi Open/Close
        for level in range(df.columns.nlevels):
            vals = [str(v).lower() for v in df.columns.get_level_values(level)]
            if "close" in vals:
                df.columns = df.columns.get_level_values(level)
                break
        else:
            df.columns = ["_".join(str(x) for x in col) for col in df.columns]

    mapping = {}
    for c in df.columns:
        cl = str(c).lower().split("_")[-1]
        if cl == "open":
            mapping[c] = "Open"
        elif cl == "high":
            mapping[c] = "High"
        elif cl == "low":
            mapping[c] = "Low"
        elif cl == "close":
            mapping[c] = "Close"
        elif cl == "volume":
            mapping[c] = "Volume"
    df = df.rename(columns=mapping)
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if "Close" not in keep:
        return pd.DataFrame()
    df = df[keep].dropna(subset=["Close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df
