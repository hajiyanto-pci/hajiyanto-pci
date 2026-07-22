"""Notifikasi hasil screening ke console / Telegram / WhatsApp / JSON."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

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
    as_of = cfg.get("as_of")
    as_of_label = as_of.isoformat() if as_of else None
    notify_cfg = cfg.get("notify", {}) or {}
    if notify_cfg.get("console", True):
        print_console(signals, mode=mode, as_of=as_of_label)
    if notify_cfg.get("save_json", True):
        save_json(
            signals,
            notify_cfg.get("output_dir", "output"),
            mode=mode,
            as_of=as_of_label,
        )
    if notify_cfg.get("telegram", True):
        send_telegram(signals, mode=mode, as_of=as_of_label)
    if notify_cfg.get("whatsapp", True):
        send_whatsapp(signals, mode=mode, as_of=as_of_label)


def _mark(ok: bool) -> str:
    return "✅" if ok else "❌"


def format_signal_block(s: Signal, *, markdown: bool = False) -> str:
    """Blok teks 1 saham dengan checklist kriteria multi-faktor."""
    c = s.checklist or {
        "volume": s.volume_ok,
        "above_ma": s.above_ma,
        "accumulation": s.accumulating,
        "breakout": s.breakout,
        "stochastic": getattr(s, "stoch_ok", False),
        "money_flow": getattr(s, "money_flow_ok", False),
        "macd": getattr(s, "macd_ok", False),
    }
    name = f"*{s.symbol}*" if markdown else s.symbol
    stoch_k = getattr(s, "stoch_k", 0)
    cmf = getattr(s, "cmf", 0)
    lines = [
        f"{name} | skor {s.score} | harga {s.price:,.0f}",
        f"{_mark(c.get('volume', False))} Volume {s.volume_ratio:.1f}x",
        f"{_mark(c.get('above_ma', False))} Di atas MA ({s.ma:,.0f})",
        f"{_mark(c.get('accumulation', False))} Akumulasi OBV",
        f"{_mark(c.get('breakout', False))} Break resistance "
        f"({s.resistance:,.0f}, +{s.breakout_pct:.1f}%)",
        f"{_mark(c.get('stochastic', False))} Stochastic %K {stoch_k:.0f}",
        f"{_mark(c.get('money_flow', False))} Money-flow/CMF {cmf:.2f}",
        f"{_mark(c.get('macd', False))} MACD",
    ]
    return "\n".join(lines)


def build_message(
    signals: list[Signal],
    mode: str,
    *,
    markdown: bool = False,
    as_of: str | None = None,
) -> str:
    title = MODE_TITLE.get(mode, mode)
    if as_of:
        title = f"Analisa {as_of}"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if markdown:
        header = f"🚀 *Stock Screener IDX — {title}*\nWaktu: {stamp}\n"
    else:
        header = f"Stock Screener IDX — {title}\nWaktu: {stamp}\n"

    if not signals:
        return header + "\nTidak ada saham yang memenuhi kriteria."

    parts = [header + f"Ditemukan: {len(signals)} saham kandidat naik\n"]
    for s in signals[:12]:
        parts.append(format_signal_block(s, markdown=markdown))
        parts.append("")
    if len(signals) > 12:
        parts.append(f"...dan {len(signals) - 12} saham lainnya")
    return "\n".join(parts).strip()


def print_console(
    signals: list[Signal], mode: str = "eod", as_of: str | None = None
) -> None:
    title = f"Analisa {as_of}" if as_of else MODE_TITLE.get(mode, mode)
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
            f"{getattr(s, 'stoch_k', 0):.0f}",
            f"{getattr(s, 'cmf', 0):.2f}",
            "Ya" if s.above_ma else "Tidak",
            "Ya" if s.accumulating else "Tidak",
            f"+{s.breakout_pct:.1f}%",
        ]
        for s in signals
    ]
    headers = [
        "Kode",
        "Skor",
        "Harga",
        "Vol",
        "StochK",
        "CMF",
        "Di atas MA",
        "Akumulasi",
        "Break",
    ]
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print("\nChecklist:")
    for s in signals:
        print(format_signal_block(s, markdown=False))
        print()


def save_json(
    signals: list[Signal],
    output_dir: str,
    mode: str = "eod",
    as_of: str | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = as_of.replace("-", "") if as_of else mode
    path = out / f"signals_{tag}_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "as_of": as_of,
        "count": len(signals),
        "signals": [s.to_dict() for s in signals],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest = out / f"signals_latest_{tag}.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if mode == "eod" and as_of is None:
        (out / "signals_latest.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    print(f"\nHasil disimpan: {path}")
    return path


def discover_telegram_chat_id(
    token: str | None = None,
    *,
    wait_seconds: int = 90,
    poll_every: float = 3.0,
) -> str | None:
    """Ambil chat_id dari update Telegram setelah user chat bot.

    Langkah user:
    1) Buka t.me/<bot_username>
    2) Tekan Start / kirim /start
    3) Jalankan perintah ini; chat_id akan muncul otomatis.
    """
    import time

    token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        print(
            "Token belum ada. Isi TELEGRAM_BOT_TOKEN di .env "
            "atau jalankan: python run_screener.py --get-chat-id --token <TOKEN>"
        )
        return None

    me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    me.raise_for_status()
    payload = me.json()
    if not payload.get("ok"):
        print(f"Token tidak valid: {payload}")
        return None
    username = payload["result"].get("username", "bot")
    print(f"Bot OK: @{username}")
    print(f"1) Buka: https://t.me/{username}")
    print("2) Tekan Start / kirim pesan: /start")
    print(f"3) Menunggu chat_id hingga {wait_seconds} detik...\n")

    # Hapus offset lama supaya update baru lebih mudah terbaca
    requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": -1},
        timeout=20,
    )

    deadline = time.time() + wait_seconds
    seen: set[str] = set()
    while time.time() < deadline:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"timeout": 5},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        for upd in data.get("result", []):
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            chat_id_s = str(chat_id)
            if chat_id_s in seen:
                continue
            seen.add(chat_id_s)
            name = (
                chat.get("username")
                or " ".join(
                    x for x in [chat.get("first_name"), chat.get("last_name")] if x
                )
                or chat.get("title")
                or "-"
            )
            print("✅ Chat ID ditemukan!")
            print(f"   chat_id : {chat_id_s}")
            print(f"   dari    : {name}")
            print("\nMasukkan ke file .env:")
            print(f"TELEGRAM_BOT_TOKEN={token}")
            print(f"TELEGRAM_CHAT_ID={chat_id_s}")
            return chat_id_s
        remaining = int(deadline - time.time())
        print(f"... belum ada pesan. Sisa {remaining}s. Pastikan sudah /start di bot.")
        time.sleep(poll_every)

    print(
        "\nTimeout: belum ada pesan ke bot.\n"
        f"Buka https://t.me/{username} → Start → jalankan lagi --get-chat-id"
    )
    return None


def write_telegram_env(token: str, chat_id: str, env_path: str | Path = ".env") -> Path:
    """Tulis/update TELEGRAM_* di .env tanpa menimpa key lain."""
    path = Path(env_path)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    def upsert(key: str, value: str) -> None:
        nonlocal lines
        prefix = f"{key}="
        for i, line in enumerate(lines):
            if line.startswith(prefix) or line.startswith(f"# {prefix}"):
                lines[i] = f"{key}={value}"
                return
        lines.append(f"{key}={value}")

    upsert("TELEGRAM_BOT_TOKEN", token)
    upsert("TELEGRAM_CHAT_ID", str(chat_id))
    if not any(l.startswith("WHATSAPP_PHONE=") for l in lines):
        # biarkan template WA tetap ada jika file baru
        pass
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"\nTersimpan ke {path.resolve()}")
    return path


def send_telegram(
    signals: list[Signal], mode: str = "eod", as_of: str | None = None
) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(
            "\n[Info] Telegram belum aktif. "
            "Isi TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di .env "
            "(lihat docs/NOTIFIKASI.md)"
        )
        return False

    text = build_message(signals, mode, markdown=True, as_of=as_of)
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


def send_whatsapp(
    signals: list[Signal], mode: str = "eod", as_of: str | None = None
) -> bool:
    """Kirim WhatsApp via CallMeBot (pribadi) atau Twilio (opsional)."""
    text = build_message(signals, mode, markdown=False, as_of=as_of)

    # Prefer CallMeBot jika dikonfigurasi
    phone = os.getenv("WHATSAPP_PHONE", "").strip()
    apikey = os.getenv("CALLMEBOT_APIKEY", "").strip()
    if phone and apikey:
        return _send_callmebot(phone, apikey, text)

    # Fallback Twilio WhatsApp
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    twilio_to = os.getenv("TWILIO_WHATSAPP_TO", "").strip()
    if twilio_sid and twilio_token and twilio_from and twilio_to:
        return _send_twilio_whatsapp(twilio_sid, twilio_token, twilio_from, twilio_to, text)

    print(
        "\n[Info] WhatsApp belum aktif. "
        "Isi WHATSAPP_PHONE + CALLMEBOT_APIKEY di .env "
        "(lihat docs/NOTIFIKASI.md)"
    )
    return False


def _send_callmebot(phone: str, apikey: str, text: str) -> bool:
    # CallMeBot: https://www.callmebot.com/blog/free-api-whatsapp-messages/
    phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={quote(phone)}&text={quote(text)}&apikey={quote(apikey)}"
    )
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        print("\nNotifikasi WhatsApp (CallMeBot) terkirim.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Gagal kirim WhatsApp CallMeBot: %s", exc)
        print(f"\n[Error] Gagal kirim WhatsApp: {exc}")
        return False


def _send_twilio_whatsapp(
    sid: str, token: str, from_num: str, to_num: str, text: str
) -> bool:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {
        "From": from_num if from_num.startswith("whatsapp:") else f"whatsapp:{from_num}",
        "To": to_num if to_num.startswith("whatsapp:") else f"whatsapp:{to_num}",
        "Body": text[:1500],
    }
    try:
        resp = requests.post(url, data=data, auth=(sid, token), timeout=30)
        resp.raise_for_status()
        print("\nNotifikasi WhatsApp (Twilio) terkirim.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Gagal kirim WhatsApp Twilio: %s", exc)
        print(f"\n[Error] Gagal kirim WhatsApp Twilio: {exc}")
        return False


def send_test_notifications() -> int:
    """Kirim pesan uji ke channel yang sudah dikonfigurasi."""
    demo = Signal(
        symbol="DEMO",
        price=1000,
        volume=5_000_000,
        volume_ratio=2.5,
        resistance=980,
        breakout_pct=2.0,
        rsi=58.0,
        ma=970,
        above_ma=True,
        accumulating=True,
        breakout=True,
        volume_ok=True,
        score=88.0,
        reasons=["Pesan uji konfigurasi notifikasi"],
        checklist={
            "volume": True,
            "above_ma": True,
            "accumulation": True,
            "breakout": True,
        },
        mode="eod",
    )
    print("Mengirim pesan uji notifikasi...")
    tg = send_telegram([demo], mode="eod")
    wa = send_whatsapp([demo], mode="eod")
    if not tg and not wa:
        print(
            "\nBelum ada channel aktif. Ikuti langkah di docs/NOTIFIKASI.md "
            "lalu isi file .env"
        )
        return 1
    return 0


def print_setup_guide() -> None:
    guide = Path("docs/NOTIFIKASI.md")
    if guide.exists():
        print(guide.read_text(encoding="utf-8"))
    else:
        print("Lihat docs/NOTIFIKASI.md untuk panduan setup Telegram & WhatsApp.")
