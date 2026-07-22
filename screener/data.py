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

    # Download batch; yfinance returns MultiIndex columns when multiple tickers.
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
        df = data.copy()
        df = _normalize_ohlcv(df)
        if not df.empty:
            result[sym] = df
        return result

    for sym in yahoo_symbols:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if sym not in data.columns.get_level_values(0):
                    continue
                df = data[sym].copy()
            else:
                df = data.copy()
            df = _normalize_ohlcv(df)
            if df.empty or len(df) < 30:
                continue
            result[sym] = df
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gagal parse %s: %s", sym, exc)
    return result


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    mapping = {}
    for c in df.columns:
        cl = str(c).lower()
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
    df = df[keep].dropna(subset=["Close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df
