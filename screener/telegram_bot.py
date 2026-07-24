"""Telegram bot interaktif untuk cek saham potensi naik & analisa 1 ticker.

Contoh natural:
  cek saham potensi kemarin
  saham hari ini
  please cek saham emtk
  /kemarin
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from screener.alerts import add_watch, load_watchlist, remove_watch, run_breakout_alert_job
from screener.analyze import analyze_stock, format_stock_report
from screener.intent import parse_user_intent
from screener.notifier import build_message
from screener.runner import run_screen

logger = logging.getLogger(__name__)

HELP_TEXT = """📈 Saham Gacor Bot

Bisa pakai bahasa natural, contoh:

• cek saham potensi kemarin
• saham hari ini
• cek tanggal 20 july
• please cek saham emtk
• /watch EMTK
• /breakout

Perintah singkat:
/kemarin | /hariini | /help | /watchlist
"""


def _api(token: str, method: str, **params: Any) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    timeout = 90 if method == "getUpdates" else 60
    resp = requests.post(url, json=params, timeout=timeout)
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


def _run_screen_and_reply(
    token: str, chat_id: str | int, *, label: str, as_of_arg: str | None
) -> None:
    send_text(
        token,
        chat_id,
        f"⏳ Memindai saham potensi naik ({label})...\nTunggu 10–40 detik.",
    )
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


def handle_command(token: str, chat_id: str | int, text: str) -> None:
    intent = parse_user_intent(text)
    logger.info("Intent: %s | raw=%r", intent.kind, intent.raw)

    if intent.kind == "help":
        send_text(token, chat_id, HELP_TEXT)
        return

    if intent.kind == "watchlist":
        syms = load_watchlist()
        if not syms:
            send_text(token, chat_id, "Watchlist kosong. Contoh: /watch EMTK")
        else:
            send_text(token, chat_id, "Watchlist:\n" + ", ".join(syms))
        return

    if intent.kind == "watch" and intent.stock_code:
        syms = add_watch(intent.stock_code)
        send_text(
            token,
            chat_id,
            f"✅ {intent.stock_code} ditambahkan ke watchlist.\n"
            f"Daftar: {', '.join(syms)}\n"
            "Kamu akan dapat notif jika baru break resistance.",
        )
        return

    if intent.kind == "unwatch" and intent.stock_code:
        syms = remove_watch(intent.stock_code)
        send_text(
            token,
            chat_id,
            f"🗑️ {intent.stock_code} dihapus dari watchlist.\n"
            f"Sisa: {', '.join(syms) if syms else '(kosong)'}",
        )
        return

    if intent.kind == "breakout":
        send_text(token, chat_id, "⏳ Cek breakout resistance baru...")
        try:
            pending = run_breakout_alert_job(
                mode="manual",
                telegram=True,
                only_watchlist=False,
            )
            if not pending:
                send_text(token, chat_id, "Tidak ada breakout BARU saat ini.")
        except Exception as exc:  # noqa: BLE001
            send_text(token, chat_id, f"❌ Gagal cek breakout: {exc}")
        return

    if intent.kind == "stock" and intent.stock_code:
        code = intent.stock_code
        send_text(token, chat_id, f"⏳ Analisa teknikal {code}...\nTunggu sebentar.")
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

    if intent.kind == "screen":
        label = intent.screen_label or "terbaru"
        as_of_arg = intent.as_of.isoformat() if intent.as_of is not None else None
        try:
            _run_screen_and_reply(token, chat_id, label=label, as_of_arg=as_of_arg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal screening")
            send_text(token, chat_id, f"❌ Gagal analisa: {exc}")
        return

    send_text(
        token,
        chat_id,
        "Maaf, saya belum yakin maksudnya.\n\n"
        "Coba contoh ini:\n"
        "• cek saham potensi kemarin\n"
        "• saham hari ini\n"
        "• please cek saham emtk\n"
        "• /help",
    )


def poll_forever(token: str, allowed_chat_id: str | None = None) -> None:
    try:
        _api(token, "deleteWebhook", drop_pending_updates=False)
    except Exception:  # noqa: BLE001
        pass

    offset = None
    print("Bot online. Contoh chat natural:")
    print("  cek saham potensi kemarin")
    print("  saham hari ini")
    print("  please cek saham emtk")
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
