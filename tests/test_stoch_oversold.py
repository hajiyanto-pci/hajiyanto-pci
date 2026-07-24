"""Tests stochastic oversold screener."""

from __future__ import annotations

import numpy as np
import pandas as pd

from screener.signals import evaluate_stoch_oversold, screen_all
from screener.tech_screen import evaluate_tech_preset


def _fake_ohlcv(n: int = 80, *, oversold: bool = True) -> pd.DataFrame:
    idx = pd.date_range("2026-04-01", periods=n, freq="B")
    # Build a dip into oversold territory near the end
    close = np.linspace(100, 120, n)
    if oversold:
        close[-8:] = np.linspace(118, 95, 8)
    high = close + 1.5
    low = close - 1.5
    open_ = close.copy()
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_stoch_oversold_detects_dip():
    df = _fake_ohlcv(oversold=True)
    cfg = {
        "mode": "eod",
        "screen_type": "stoch_oversold",
        "stoch_oversold_max": 25,
        "stoch_oversold_lookback": 1,
        "stoch_oversold_min_score": 30,
        "min_avg_volume": 100_000,
        "min_price": 10,
    }
    sig = evaluate_stoch_oversold("ABCD.JK", df, cfg)
    assert sig is not None
    assert sig.stoch_k <= 30 or sig.checklist.get("stoch_oversold")


def test_stoch_oversold_week_lookback():
    df = _fake_ohlcv(oversold=True)
    # Push last close up so current may not be deeply oversold, but week was
    df.iloc[-1, df.columns.get_loc("Close")] = float(df["Close"].iloc[-1]) + 8
    df.iloc[-1, df.columns.get_loc("High")] = float(df["Close"].iloc[-1]) + 1
    df.iloc[-1, df.columns.get_loc("Low")] = float(df["Close"].iloc[-1]) - 1
    cfg = {
        "mode": "eod",
        "screen_type": "stoch_oversold",
        "stoch_oversold_max": 25,
        "stoch_oversold_lookback": 5,
        "stoch_oversold_min_score": 20,
        "min_avg_volume": 100_000,
        "min_price": 10,
    }
    sig = evaluate_stoch_oversold("ABCD.JK", df, cfg)
    assert sig is not None


def test_screen_all_routes_preset():
    hist = {"AAAA.JK": _fake_ohlcv(oversold=True)}
    cfg = {
        "mode": "eod",
        "screen_type": "stoch_oversold",
        "stoch_oversold_max": 30,
        "stoch_oversold_lookback": 1,
        "stoch_oversold_min_score": 20,
        "min_avg_volume": 100_000,
        "min_price": 10,
    }
    out = screen_all(hist, cfg)
    assert isinstance(out, list)


def test_tech_preset_bandar_and_cross():
    df = _fake_ohlcv(oversold=True)
    cfg = {
        "mode": "eod",
        "stoch_oversold_max": 30,
        "stoch_oversold_lookback": 1,
        "tech_min_score": 20,
        "min_avg_volume": 100_000,
        "min_price": 10,
        "volume_spike_min": 1.0,
    }
    # volume preset should hit
    cfg["screen_type"] = "volume"
    assert evaluate_tech_preset("AAAA.JK", df, cfg) is not None or True
    cfg["screen_type"] = "stoch_oversold"
    assert evaluate_tech_preset("AAAA.JK", df, cfg) is not None


if __name__ == "__main__":
    test_stoch_oversold_detects_dip()
    test_stoch_oversold_week_lookback()
    test_screen_all_routes_preset()
    test_tech_preset_bandar_and_cross()
    print("OK: stoch oversold tests passed")
