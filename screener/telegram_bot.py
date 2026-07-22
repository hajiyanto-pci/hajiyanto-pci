"""Telegram bot interaktif untuk cek saham potensi naik.

Contoh chat ke @Sahamgacor_bot:
  /start
  /kemarin
  /cek 2026-07-21
  /hariini
  /help

Jalankan online (proses harus hidup):
  python run_bot.py
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from screener.notifier import build_message
from screener.runner import run_screen
from screener.signals import parse_as_of

logger = logging.getLogger(__name__)

HELP_TEXT = """📈 Saham Gacor Bot

Kirim perintah:

/kemarin — analisa sesi bursa sebelumnya
/cek 2026-07-21 — analisa tanggal tertentu
/hariini — analisa data terbaru
/help — bantuan ini

Contoh:
/kemarin
/cek 2026-07-21
/cek kemarin

Bot memindai: volume, MA, akumulasi, break resistance, stochastic, money-flow, MACD.
"""


def _api(token: str, method: str, **params: Any) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.post(url, json=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    return data["result"]


def send_text(token: str, chat_id: str | int, text: str, *, markdown: bool = True) -> None:
    chunks = []
    while text:
        chunks.append(text[:3500])
        text = text[3500:]
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if markdown:
            payload["parse_mode"] = "Markdown"
        try:
            _api(token, "sendMessage", **payload)
        except Exception:
            # Fallback plain text jika Markdown gagal parse
            payload.pop("parse_mode", None)
            _api(token, "sendMessage", **payload)


def handle_command(token: str, chat_id: str | int, text: str) -> None:
    raw = (text or "").strip()
    lower = raw.lower()
    parts = lower.split()
    cmd = parts[0] if parts else ""

    if cmd in {"/start", "/help", "help", "bantuan"}:
        send_text(token, chat_id, HELP_TEXT)
        return

    as_of: str | None = None
    label = "terbaru"

    if cmd in {"/kemarin", "kemarin", "/yesterday"}:
        as_of = "kemarin"
        label = "kemarin"
    elif cmd in {"/hariini", "/today", "hariini"}:
        as_of = None
        label = "hari ini / terbaru"
    elif cmd in {"/cek", "cek", "/asof"}:
        if len(parts) < 2:
            send_text(
                token,
                chat_id,
                "Format: `/cek 2026-07-21` atau `/cek kemarin`",
            )
            return
        as_of = parts[1]
        label = as_of
    else:
        # Izinkan teks bebas: "cek kemarin" / "cek 2026-07-21"
        if lower.startswith("cek "):
            as_of = lower.split(maxsplit=1)[1].strip()
            label = as_of
        else:
            send_text(
                token,
                chat_id,
                "Perintah tidak dikenali.\n\n" + HELP_TEXT,
            )
            return

    send_text(
        token,
        chat_id,
        f"⏳ Memindai saham potensi naik (*{label}*)...\nTunggu 10–40 detik.",
    )
    try:
        parsed = parse_as_of(as_of) if as_of else None
        signals = run_screen(
            as_of=as_of,
            mode="eod",
            notify=False,
            telegram=False,
            whatsapp=False,
        )
        msg = build_message(
            signals,
            mode="eod",
            markdown=True,
            as_of=parsed.isoformat() if parsed else None,
        )
        if not signals:
            msg += (
                "\n\n_Tidak ada yang lolos filter multi-faktor. "
                "Coba tanggal lain._"
            )
        send_text(token, chat_id, msg)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gagal proses perintah")
        send_text(token, chat_id, f"❌ Gagal analisa: `{exc}`")


def poll_forever(token: str, allowed_chat_id: str | None = None) -> None:
    """Long-polling update Telegram."""
    # Hapus webhook agar getUpdates jalan
    try:
        _api(token, "deleteWebhook", drop_pending_updates=False)
    except Exception:  # noqa: BLE001
        pass

    offset = None
    print("Bot online. Chat contoh ke bot:")
    print("  /kemarin")
    print("  /cek 2026-07-21")
    print("  /hariini")
    print("Menunggu pesan... (Ctrl+C untuk stop)")

    while True:
        try:
            params: dict[str, Any] = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            updates = _api(token, "getUpdates", **params)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = msg.get("text") or ""
                if chat_id is None or not text:
                    continue
                if allowed_chat_id and str(chat_id) != str(allowed_chat_id):
                    send_text(
                        token,
                        chat_id,
                        "Bot ini pribadi. Chat_id kamu belum diizinkan.",
                    )
                    continue
                print(f"Pesan dari {chat_id}: {text}")
                handle_command(token, chat_id, text)
        except KeyboardInterrupt:
            print("Bot dihentikan.")
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("Poll error: %s", exc)
            time.sleep(3)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN belum diisi di .env")
        return 1
    allowed = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    poll_forever(token, allowed_chat_id=allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
