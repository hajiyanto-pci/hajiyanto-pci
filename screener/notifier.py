"""Notifikasi hasil screening ke console / Telegram / JSON."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from tabulate import tabulate

from screener.signals import Signal

logger = logging.getLogger(__name__)

MODE_TITLE = {
    "eod": "EOD Confirmed (sore)",
    "morning": "Watchlist Pagi (H-1)",
    "midday": "Early Alert Siang",
}


def notify_all(signals: Iterable[Signal], cfg: dict) -> None:
    signals = list(signals)
    mode = str(cfg.get("mode", "eod")).lower()
    notify_cfg = cfg.get("notify", {}) or {}
    if notify_cfg.get("console", True):
        print_console(signals, mode=mode)
    if notify_cfg.get("save_json", True):
        save_json(signals, notify_cfg.get("output_dir", "output"), mode=mode)
    if notify_cfg.get("telegram", True):
        send_telegram(signals, mode=mode)


def print_console(signals: list[Signal], mode: str = "eod") -> None:
    title = MODE_TITLE.get(mode, mode)
    print(f"\n=== HASIL SCREENING SAHAM — {title} ===")
    print(f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if not signals:
        print("Tidak ada saham yang memenuhi kriteria untuk mode ini.")
        return

    rows = [
        [
            s.symbol,
            s.score,
            s.price,
            f"{s.volume_ratio:.1f}x",
            s.resistance,
            f"+{s.breakout_pct:.1f}%",
            s.rsi,
            "Ya" if s.above_ma else "Tidak",
        ]
        for s in signals
    ]
    headers = ["Kode", "Skor", "Harga", "Vol", "Resist", "Break", "RSI", "Di atas MA"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print("\nDetail alasan:")
    for s in signals:
        print(f"- {s.symbol} (skor {s.score}): {'; '.join(s.reasons)}")


def save_json(signals: list[Signal], output_dir: str, mode: str = "eod") -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out / f"signals_{mode}_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "count": len(signals),
        "signals": [s.to_dict() for s in signals],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest = out / f"signals_latest_{mode}.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Compatibility with previous filename
    if mode == "eod":
        (out / "signals_latest.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    print(f"\nHasil disimpan: {path}")
    return path


def send_telegram(signals: list[Signal], mode: str = "eod") -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.info(
            "Telegram dilewati: set TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di .env"
        )
        print(
            "\n[Info] Notifikasi Telegram belum aktif. "
            "Isi TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di file .env"
        )
        return False

    title = MODE_TITLE.get(mode, mode)
    if not signals:
        text = (
            f"📡 *Stock Screener IDX — {title}*\n"
            f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "Tidak ada saham yang memenuhi kriteria."
        )
    else:
        lines = [
            f"🚀 *Stock Screener IDX — {title}*",
            f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Ditemukan: *{len(signals)}* saham\n",
        ]
        for s in signals[:15]:
            lines.append(
                f"*{s.symbol}* skor `{s.score}`\n"
                f"Harga {s.price:,.0f} | Vol {s.volume_ratio:.1f}x | "
                f"Break +{s.breakout_pct:.1f}% | RSI {s.rsi:.0f}\n"
                f"_{'; '.join(s.reasons[:3])}_\n"
            )
        if len(signals) > 15:
            lines.append(f"_...dan {len(signals) - 15} saham lainnya_")
        text = "\n".join(lines)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        resp.raise_for_status()
        print("\nNotifikasi Telegram terkirim.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Gagal kirim Telegram: %s", exc)
        print(f"\n[Error] Gagal kirim Telegram: {exc}")
        return False
