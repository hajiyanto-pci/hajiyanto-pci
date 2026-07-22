"""Unit test sederhana untuk logika sinyal + jadwal + akumulasi."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from screener.indicators import is_accumulating
from screener.notifier import build_message, format_signal_block
from screener.schedule import explain_schedule, recommend_primary_mode, session_progress
from screener.signals import Signal, evaluate_symbol

JAKARTA = ZoneInfo("Asia/Jakarta")


def _make_df(
    n: int = 60,
    breakout: bool = True,
    vol_spike: bool = True,
    trending_up: bool = True,
) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    if trending_up:
        base = np.linspace(1000, 1100, n)
    else:
        base = np.linspace(1100, 1000, n)
    noise = rng.normal(0, 3, n)
    close = base + noise
    if breakout:
        close[-1] = max(close[:-1].max() + 20, close[-1])
    high = close + 5
    low = close - 5
    open_ = close - 1
    volume = np.full(n, 1_000_000.0)
    # Lebih banyak volume di hari naik untuk akumulasi
    for i in range(1, n):
        if close[i] > close[i - 1]:
            volume[i] = 1_400_000.0
        else:
            volume[i] = 700_000.0
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


CFG = {
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
    "mode": "eod",
    "require_above_ma": True,
    "require_accumulation": True,
    "accumulation_lookback": 10,
}


def test_breakout_with_volume_passes():
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=True, vol_spike=True), CFG)
    assert sig is not None
    assert sig.symbol == "TEST"
    assert sig.volume_ok
    assert sig.above_ma
    assert sig.accumulating
    assert sig.breakout
    assert sig.checklist["volume"]
    assert sig.checklist["breakout"]


def test_no_breakout_filtered():
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=False, vol_spike=True), CFG)
    assert sig is None


def test_accumulation_helper():
    df = _make_df(trending_up=True)
    ok, note = is_accumulating(df["Close"], df["Volume"], lookback=10)
    assert ok is True
    assert "Akumulasi" in note or "OBV" in note


def test_message_contains_checklist():
    sig = Signal(
        symbol="BBCA",
        price=10000,
        volume=1e6,
        volume_ratio=2.0,
        resistance=9900,
        breakout_pct=1.0,
        rsi=55,
        ma=9800,
        above_ma=True,
        accumulating=True,
        breakout=True,
        volume_ok=True,
        score=80,
        reasons=["test"],
        checklist={
            "volume": True,
            "above_ma": True,
            "accumulation": True,
            "breakout": True,
        },
    )
    block = format_signal_block(sig)
    assert "Volume" in block and "Akumulasi" in block and "Break" in block
    msg = build_message([sig], "eod", markdown=False)
    assert "BBCA" in msg


def test_recommend_eod():
    assert recommend_primary_mode() == "eod"
    text = explain_schedule()
    assert "20 16" in text


def test_session_progress_bounds():
    morning = datetime(2026, 7, 22, 8, 0, tzinfo=JAKARTA)
    midday = datetime(2026, 7, 22, 11, 0, tzinfo=JAKARTA)
    evening = datetime(2026, 7, 22, 17, 0, tzinfo=JAKARTA)
    assert session_progress(morning) == 0.0
    assert 0.0 < session_progress(midday) < 1.0
    assert session_progress(evening) == 1.0


if __name__ == "__main__":
    test_breakout_with_volume_passes()
    test_no_breakout_filtered()
    test_accumulation_helper()
    test_message_contains_checklist()
    test_recommend_eod()
    test_session_progress_bounds()
    print("OK: tests passed")
