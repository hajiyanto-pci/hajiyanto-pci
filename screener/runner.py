"""Shared runner: load config, fetch data, screen, optionally notify."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from screener.data import fetch_history
from screener.notifier import notify_all
from screener.schedule import recommend_primary_mode
from screener.signals import Signal, parse_as_of, screen_all
from screener.universe import DEFAULT_IDX_SYMBOLS


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_screen(
    *,
    config_path: str | Path = "config.yaml",
    mode: str | None = None,
    as_of: str | None = None,
    symbols: list[str] | None = None,
    min_score: float | None = None,
    notify: bool = True,
    telegram: bool = True,
    whatsapp: bool = False,
) -> list[Signal]:
    cfg = load_config(config_path)
    cfg["mode"] = (mode or cfg.get("mode") or recommend_primary_mode()).lower()

    parsed = parse_as_of(as_of)
    if parsed is not None:
        cfg["as_of"] = parsed
        cfg["mode"] = "eod"

    if min_score is not None:
        cfg["min_score"] = min_score

    cfg.setdefault("notify", {})
    if not notify:
        cfg["notify"]["console"] = False
        cfg["notify"]["telegram"] = False
        cfg["notify"]["whatsapp"] = False
        cfg["notify"]["save_json"] = True
    else:
        cfg["notify"]["telegram"] = telegram
        cfg["notify"]["whatsapp"] = whatsapp
        cfg["notify"]["console"] = True
        cfg["notify"]["save_json"] = True

    syms = symbols or cfg.get("symbols") or DEFAULT_IDX_SYMBOLS
    syms = [str(s).strip().upper() for s in syms if str(s).strip()]
    market = str(cfg.get("market", "IDX"))

    histories = fetch_history(
        syms,
        history_days=int(cfg.get("history_days", 120)),
        market=market,
    )
    signals = screen_all(histories, cfg)
    if notify:
        notify_all(signals, cfg)
    return signals
