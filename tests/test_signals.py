"""Unit test multi-faktor + jadwal."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from screener.indicators import bandar_flow_score, is_accumulating, stochastic
from screener.notifier import build_message, format_signal_block
from screener.schedule import explain_schedule, recommend_primary_mode, session_progress
from screener.signals import Signal, evaluate_symbol

JAKARTA = ZoneInfo("Asia/Jakarta")


def _make_df(
    n: int = 80,
    breakout: bool = True,
    vol_spike: bool = True,
    trending_up: bool = True,
) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    if trending_up:
        base = np.linspace(1000, 1200, n)
    else:
        base = np.linspace(1200, 1000, n)
    noise = rng.normal(0, 3, n)
    close = base + noise
    if breakout:
        # Breakout moderat agar RSI/Stoch tidak ekstrem overbought
        close[-1] = max(close[:-1].max() + 8, close[-1])
    high = close + 8
    low = close - 8
    open_ = close - 1
    volume = np.full(n, 1_000_000.0)
    for i in range(1, n):
        if close[i] > close[i - 1]:
            volume[i] = 1_500_000.0
            high[i] = close[i] + 3
            low[i] = close[i] - 8
        else:
            volume[i] = 600_000.0
            high[i] = close[i] + 8
            low[i] = close[i] - 3
    if vol_spike:
        volume[-1] = 3_500_000.0
        high[-1] = close[-1] + 2
        low[-1] = close[-1] - 10
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
    "rsi_max": 95,
    "ma_period": 20,
    "min_avg_volume": 100_000,
    "min_price": 50,
    "min_score": 50,
    "mode": "eod",
    "require_above_ma": True,
    "require_accumulation": True,
    "require_money_flow": False,
    "require_stoch": False,
    "accumulation_lookback": 10,
}


def test_breakout_with_volume_passes():
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=True, vol_spike=True), CFG)
    assert sig is not None
    assert sig.symbol == "TEST"
    assert sig.volume_ok
    assert sig.above_ma
    assert sig.breakout
    assert "volume" in sig.factor_scores


def test_no_breakout_filtered():
    sig = evaluate_symbol("TEST.JK", _make_df(breakout=False, vol_spike=True), CFG)
    assert sig is None


def test_indicators():
    df = _make_df()
    ok, note = is_accumulating(df["Close"], df["Volume"], lookback=10)
    assert ok is True
    k, d = stochastic(df["High"], df["Low"], df["Close"])
    assert np.isfinite(k.iloc[-1])
    flow_ok, pts, _ = bandar_flow_score(df["High"], df["Low"], df["Close"], df["Volume"])
    assert pts >= 0


def test_message_contains_checklist():
    sig = Signal(
        symbol="BBCA",
        price=10000,
        volume=1e6,
        volume_ratio=2.0,
        resistance=9900,
        breakout_pct=1.0,
        rsi=55,
        stoch_k=60,
        stoch_d=55,
        cmf=0.12,
        mfi=58,
        macd_hist=1.2,
        ma=9800,
        above_ma=True,
        accumulating=True,
        breakout=True,
        volume_ok=True,
        stoch_ok=True,
        money_flow_ok=True,
        macd_ok=True,
        score=80,
        factor_scores={"volume": 16},
        reasons=["test"],
        checklist={
            "volume": True,
            "above_ma": True,
            "accumulation": True,
            "breakout": True,
            "stochastic": True,
            "money_flow": True,
            "macd": True,
        },
    )
    block = format_signal_block(sig)
    assert "Stochastic" in block and "Money-flow" in block
    assert "BBCA" in build_message([sig], "eod")


def test_recommend_eod():
    assert recommend_primary_mode() == "eod"
    assert "20 16" in explain_schedule()


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
    test_indicators()
    test_message_contains_checklist()
    test_recommend_eod()
    test_session_progress_bounds()
    print("OK: tests passed")
