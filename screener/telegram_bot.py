"""Telegram bot interaktif untuk cek saham potensi naik & analisa 1 ticker.

Contoh:
  /kemarin
  cek tanggal 20 july
  please cek saham emtk
  cek emtk
  /saham BBCA
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from screener.analyze import analyze_stock, format_stock_report
from screener.dates import extract_date_query
from screener.intent import extract_stock_code
from screener.notifier import build_message
from screener.runner import run_screen

logger = logging.getLogger(__name__)

HELP_TEXT = """📈 Saham Gacor Bot

1) Screening banyak saham:
/kemarin
cek tanggal 20 july
cek 20/07/2026
/hariini

2) Analisa 1 saham + saran keputusan:
please cek saham emtk
cek saham BBCA
cek emtk
/saham EMTK

Hasil mencakup skor, MA, volume, breakout, stochastic, money-flow,
Entry / SL / TP1 / TP2, dan saran ke depan.

Jadwal otomatis: 09:10 open | 12:05 break sesi 1 | 16:20 EOD
"""


def _api(token: str, method: str, **params: Any) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.post(url, json=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    return data["result"]


def send_text(token: str, chat_id: str | int, text: str, *, markdown: bool = False) -> None:
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
            payload.pop("parse_mode", None)
            _api(token, "sendMessage", **payload)


def handle_command(token: str, chat_id: str | int, text: str) -> None:
    raw = (text or "").strip()
    lower = raw.lower().strip()

    if lower in {"/start", "/help", "help", "bantuan"}:
        send_text(token, chat_id, HELP_TEXT)
        return

    # Prioritas: query 1 saham
    code = extract_stock_code(raw)
    if code:
        send_text(
            token,
            chat_id,
            f"⏳ Analisa teknikal {code}...\nTunggu sebentar.",
        )
        try:
            report = analyze_stock(code)
            send_text(token, chat_id, format_stock_report(report))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal analisa saham")
            send_text(
                token,
                chat_id,
                f"❌ Gagal analisa {code}: {exc}\n"
                "Pastikan kode saham BEI benar (contoh EMTK, BBCA).",
            )
        return

    # Screening by date
    try:
        label, as_of_date = extract_date_query(raw)
    except ValueError as exc:
        msg = str(exc)
        if msg == "__HELP__":
            send_text(token, chat_id, HELP_TEXT)
            return
        send_text(token, chat_id, f"{msg}\n\n{HELP_TEXT}")
        return

    as_of_arg = as_of_date.isoformat() if as_of_date is not None else None
    send_text(
        token,
        chat_id,
        f"⏳ Memindai saham potensi naik ({label})...\nTunggu 10–40 detik.",
    )
    try:
        signals = run_screen(
            as_of=as_of_arg,
            mode="eod",
            notify=False,
            telegram=False,
            whatsapp=False,
        )
        msg = build_message(
            signals,
            mode="eod",
            markdown=False,
            as_of=as_of_arg,
        )
        if not signals:
            msg += "\n\nTidak ada yang lolos filter. Coba tanggal lain."
        send_text(token, chat_id, msg)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gagal proses perintah")
        send_text(token, chat_id, f"❌ Gagal analisa: {exc}")


def poll_forever(token: str, allowed_chat_id: str | None = None) -> None:
    try:
        _api(token, "deleteWebhook", drop_pending_updates=False)
    except Exception:  # noqa: BLE001
        pass

    offset = None
    print("Bot online. Contoh chat:")
    print("  please cek saham emtk")
    print("  /kemarin")
    print("  cek tanggal 20 july")
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
