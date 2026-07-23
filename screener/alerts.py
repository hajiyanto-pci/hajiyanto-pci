"""Notifikasi otomatis saat saham BARU break resistance.

Anti-spam: state disimpan di output/breakout_alerts_state.json
supaya breakout yang sama tidak dikirim berulang di hari yang sama.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

from screener.data import fetch_history
from screener.indicators import pct_change, resistance_level, suggest_sl_tp
from screener.universe import DEFAULT_IDX_SYMBOLS, from_yahoo_symbol

logger = logging.getLogger(__name__)
JAKARTA = ZoneInfo("Asia/Jakarta")

WATCHLIST_PATH = Path("output/watchlist.json")
STATE_PATH = Path("output/breakout_alerts_state.json")


@dataclass
class BreakoutAlert:
    symbol: str
    price: float
    resistance: float
    breakout_pct: float
    volume_ratio: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    risk_pct: float
    tp1_pct: float
    tp2_pct: float
    bar_date: str
    fresh: bool

def load_watchlist(path: Path = WATCHLIST_PATH) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        syms = data.get("symbols", data if isinstance(data, list) else [])
        return sorted({str(s).strip().upper() for s in syms if str(s).strip()})
    except Exception:  # noqa: BLE001
        return []


def save_watchlist(symbols: list[str], path: Path = WATCHLIST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(JAKARTA).isoformat(),
        "symbols": sorted({s.upper() for s in symbols}),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_watch(symbol: str, path: Path = WATCHLIST_PATH) -> list[str]:
    syms = load_watchlist(path)
    code = symbol.strip().upper().replace(".JK", "")
    if code and code not in syms:
        syms.append(code)
        save_watchlist(syms, path)
    return load_watchlist(path)


def remove_watch(symbol: str, path: Path = WATCHLIST_PATH) -> list[str]:
    code = symbol.strip().upper().replace(".JK", "")
    syms = [s for s in load_watchlist(path) if s != code]
    save_watchlist(syms, path)
    return syms


def _load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"alerts": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"alerts": {}}


def _save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _bar_date_str(idx_value) -> str:
    ts = pd.Timestamp(idx_value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(JAKARTA)
    else:
        ts = ts.tz_convert(JAKARTA)
    return ts.date().isoformat()


def detect_fresh_breakout(
    yahoo_symbol: str,
    df: pd.DataFrame,
    *,
    resistance_lookback: int = 20,
    min_avg_volume: float = 300_000,
    min_price: float = 50,
    require_volume_ratio: float = 1.0,
) -> BreakoutAlert | None:
    """Fresh = close sekarang >= resistance, close sebelumnya < resistance."""
    if df is None or len(df) < resistance_lookback + 3:
        return None

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    if last_close < min_price:
        return None

    avg_vol = float(volume.iloc[-(21):-1].mean())
    if not np.isfinite(avg_vol) or avg_vol < min_avg_volume:
        return None
    vol_ratio = float(volume.iloc[-1]) / avg_vol if avg_vol > 0 else 0.0
    if vol_ratio < require_volume_ratio:
        return None

    # Resistance dari high sebelum hari ini
    resist = resistance_level(high, resistance_lookback)
    if resist is None or resist <= 0:
        return None

    broken_now = last_close >= resist
    broken_prev = prev_close >= resist
    if not broken_now:
        return None

    fresh = broken_now and not broken_prev
    levels = suggest_sl_tp(last_close, high, low, close)

    return BreakoutAlert(
        symbol=from_yahoo_symbol(yahoo_symbol),
        price=round(last_close, 2),
        resistance=round(float(resist), 2),
        breakout_pct=round(pct_change(last_close, float(resist)), 2),
        volume_ratio=round(vol_ratio, 2),
        entry=levels["entry"],
        sl=levels["sl"],
        tp1=levels["tp1"],
        tp2=levels["tp2"],
        risk_pct=levels["risk_pct"],
        tp1_pct=levels["tp1_pct"],
        tp2_pct=levels["tp2_pct"],
        bar_date=_bar_date_str(df.index[-1]),
        fresh=fresh,
    )


def scan_breakout_alerts(
    *,
    config_path: str | Path = "config.yaml",
    symbols: list[str] | None = None,
    only_fresh: bool = True,
    only_watchlist: bool = False,
) -> list[BreakoutAlert]:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    watch = load_watchlist()
    if only_watchlist:
        syms = watch
    else:
        base = symbols or cfg.get("symbols") or DEFAULT_IDX_SYMBOLS
        syms = sorted(set([*(str(s).upper() for s in base), *watch]))

    if not syms:
        return []

    histories = fetch_history(
        syms,
        history_days=int(cfg.get("history_days", 120)),
        market=str(cfg.get("market", "IDX")),
    )

    alerts: list[BreakoutAlert] = []
    for yahoo, df in histories.items():
        alert = detect_fresh_breakout(
            yahoo,
            df,
            resistance_lookback=int(cfg.get("resistance_lookback", 20)),
            min_avg_volume=float(cfg.get("breakout_alert_min_avg_volume", 300_000)),
            min_price=float(cfg.get("min_price", 50)),
            require_volume_ratio=float(cfg.get("breakout_alert_min_volume_ratio", 1.0)),
        )
        if alert is None:
            continue
        if only_fresh and not alert.fresh:
            continue
        alerts.append(alert)
    alerts.sort(key=lambda a: a.breakout_pct, reverse=True)
    return alerts


def filter_unsent(alerts: list[BreakoutAlert], state_path: Path = STATE_PATH) -> list[BreakoutAlert]:
    state = _load_state(state_path)
    sent = state.setdefault("alerts", {})
    fresh: list[BreakoutAlert] = []
    for a in alerts:
        key = f"{a.symbol}:{a.bar_date}"
        if key in sent:
            continue
        fresh.append(a)
    return fresh


def mark_sent(alerts: list[BreakoutAlert], state_path: Path = STATE_PATH) -> None:
    state = _load_state(state_path)
    sent = state.setdefault("alerts", {})
    now = datetime.now(JAKARTA).isoformat()
    for a in alerts:
        key = f"{a.symbol}:{a.bar_date}"
        sent[key] = {"sent_at": now, **asdict(a)}
    # trim lama (keep last 500)
    if len(sent) > 500:
        keys = sorted(sent.keys())
        for k in keys[: len(sent) - 500]:
            sent.pop(k, None)
    state["updated_at"] = now
    _save_state(state, state_path)


def format_breakout_message(alerts: list[BreakoutAlert], *, mode: str = "") -> str:
    title = "🚨 BREAK RESISTANCE ALERT"
    if mode:
        title += f" ({mode})"
    stamp = datetime.now(JAKARTA).strftime("%Y-%m-%d %H:%M")
    if not alerts:
        return f"{title}\nWaktu: {stamp}\n\nTidak ada breakout baru."

    lines = [
        title,
        f"Waktu: {stamp}",
        f"Breakout baru: {len(alerts)} saham\n",
    ]
    for a in alerts[:15]:
        lines.extend(
            [
                f"*{a.symbol}* break +{a.breakout_pct:.1f}%",
                f"Harga {a.price:,.0f} > resist {a.resistance:,.0f} | Vol {a.volume_ratio:.1f}x",
                f"🎯 Entry ~{a.entry:,.0f}",
                f"🛑 SL {a.sl:,.0f} (-{a.risk_pct:.1f}%)",
                f"✅ TP1 {a.tp1:,.0f} (+{a.tp1_pct:.1f}%) | TP2 {a.tp2:,.0f} (+{a.tp2_pct:.1f}%)",
                "",
            ]
        )
    if len(alerts) > 15:
        lines.append(f"...dan {len(alerts) - 15} lainnya")
    return "\n".join(lines).strip()


def run_breakout_alert_job(
    *,
    config_path: str | Path = "config.yaml",
    mode: str = "",
    telegram: bool = True,
    only_watchlist: bool = False,
    force_resend: bool = False,
) -> list[BreakoutAlert]:
    alerts = scan_breakout_alerts(
        config_path=config_path,
        only_fresh=True,
        only_watchlist=only_watchlist,
    )
    pending = alerts if force_resend else filter_unsent(alerts)
    print(f"Breakout fresh terdeteksi: {len(alerts)} | belum dikirim: {len(pending)}")

    msg = format_breakout_message(pending, mode=mode)
    print(msg)

    if pending and telegram:
        import os

        import requests

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and chat_id:
            plain = msg.replace("*", "")
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": plain[:3900],
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            mark_sent(pending)
            print("Notifikasi breakout Telegram terkirim.")
        else:
            print("Telegram belum dikonfigurasi; skip kirim.")
    elif pending:
        mark_sent(pending)

    # simpan snapshot
    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JAKARTA).strftime("%Y%m%d_%H%M%S")
    (out / f"breakout_alerts_{stamp}.json").write_text(
        json.dumps([asdict(a) for a in pending], indent=2),
        encoding="utf-8",
    )
    return pending
