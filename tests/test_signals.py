"""Unit test sederhana untuk logika sinyal."""

from __future__ import annotations

import numpy as np
import pandas as pd

from screener.signals import evaluate_symbol


def _make_df(n: int = 60, breakout: bool = True, vol_spike: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(1000, 1100, n)
    noise = rng.normal(0, 5, n)
    close = base + noise
    if breakout:
        close[-1] = max(close[:-1].max() + 20, close[-1])
    high = close + 5
    low = close - 5
    open_ = close - 1
    volume = np.full(n, 1_000_000.0)
    if vol_spike:
        volume[-1] = 3_000_000.0
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def test_breakout_with_volume_passes():
    cfg = {
        "volume_avg_days": 20,
        "volume_spike_min": 1.5,
        "resistance_lookback": 20,
        "breakout_buffer_pct": 0.0,
        "rsi_period": 14,
        "rsi_max": 90,
        "ma_period": 20,
        "min_avg_volume": 100_000,
        "min_price": 50,
        "min_score": 50,
    }
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=True, vol_spike=True), cfg)
    assert sig is not None
    assert sig.symbol == "TEST"
    assert sig.volume_ratio >= 1.5
    assert sig.breakout_pct > 0


def test_no_breakout_filtered():
    cfg = {
        "volume_avg_days": 20,
        "volume_spike_min": 1.5,
        "resistance_lookback": 20,
        "breakout_buffer_pct": 0.0,
        "rsi_period": 14,
        "rsi_max": 90,
        "ma_period": 20,
        "min_avg_volume": 100_000,
        "min_price": 50,
        "min_score": 50,
    }
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=False, vol_spike=True), cfg)
    assert sig is None


if __name__ == "__main__":
    test_breakout_with_volume_passes()
    test_no_breakout_filtered()
    print("OK: tests passed")
