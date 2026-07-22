"""Jadwal notifikasi vs jam pasar BEI + rekomendasi mode screening."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")

# Jam resmi pasar reguler BEI (WIB)
MARKET = {
    "pre_open_start": time(8, 45),
    "session1_start": time(9, 0),
    "session1_end_weekday": time(12, 0),
    "session1_end_friday": time(11, 30),
    "session2_start_weekday": time(13, 30),
    "session2_start_friday": time(14, 0),
    "session2_end": time(15, 50),
    "close_done": time(16, 15),
}

MODES = ("morning", "open", "midday", "eod")


@dataclass(frozen=True)
class ScheduleAdvice:
    mode: str
    recommended_cron: str
    purpose: str
    reliability: str
    best_for: str


ADVICE: dict[str, ScheduleAdvice] = {
    "eod": ScheduleAdvice(
        mode="eod",
        recommended_cron="20 16 * * 1-5",
        purpose="Konfirmasi breakout + volume penuh setelah market close",
        reliability="Tinggi (data harian lengkap: close & volume final)",
        best_for="Keputusan utama + SL/TP final paling andal",
    ),
    "open": ScheduleAdvice(
        mode="open",
        recommended_cron="10 9 * * 1-5",
        purpose="Pantau potensi naik & volume awal setelah market open",
        reliability="Rendah-sedang (baru ~10 menit perdagangan)",
        best_for="Early watchlist intraday jam 09:10",
    ),
    "midday": ScheduleAdvice(
        mode="midday",
        recommended_cron="5 12 * * 1-5",
        purpose="Cek volume & breakout di break sesi 1",
        reliability="Sedang (volume sesi 1 sudah terkumpul, belum final EOD)",
        best_for="Seleksi kandidat sebelum sesi 2",
    ),
    "morning": ScheduleAdvice(
        mode="morning",
        recommended_cron="30 8 * * 1-5",
        purpose="Watchlist dari breakout kemarin untuk antisipasi di open",
        reliability="Sedang (berdasarkan sinyal H-1 yang sudah confirmed)",
        best_for="Persiapan order pagi",
    ),
}


def now_jakarta(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JAKARTA)
    if now.tzinfo is None:
        return now.replace(tzinfo=JAKARTA)
    return now.astimezone(JAKARTA)


def is_friday(now: datetime | None = None) -> bool:
    return now_jakarta(now).weekday() == 4


def session_progress(now: datetime | None = None) -> float:
    """Perkiraan fraksi sesi reguler yang sudah berjalan (0..1)."""
    n = now_jakarta(now)
    t = n.time()
    fri = is_friday(n)

    s1_start = MARKET["session1_start"]
    s1_end = MARKET["session1_end_friday"] if fri else MARKET["session1_end_weekday"]
    s2_start = MARKET["session2_start_friday"] if fri else MARKET["session2_start_weekday"]
    s2_end = MARKET["session2_end"]

    def minutes(a: time, b: time) -> float:
        return (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)

    total = minutes(s1_start, s1_end) + minutes(s2_start, s2_end)
    if total <= 0:
        return 0.0

    def to_min(x: time) -> int:
        return x.hour * 60 + x.minute

    cur = to_min(t)
    elapsed = 0.0
    if cur <= to_min(s1_start):
        elapsed = 0.0
    elif cur < to_min(s1_end):
        elapsed = cur - to_min(s1_start)
    elif cur < to_min(s2_start):
        elapsed = minutes(s1_start, s1_end)
    elif cur < to_min(s2_end):
        elapsed = minutes(s1_start, s1_end) + (cur - to_min(s2_start))
    else:
        elapsed = total
    return max(0.0, min(1.0, elapsed / total))


def recommend_primary_mode() -> str:
    return "eod"


def explain_schedule() -> str:
    lines = [
        "=== REKOMENDASI JADWAL NOTIFIKASI (BEI / IDX) ===",
        "",
        "Jam pasar reguler (WIB):",
        "  Pre-open  08:45–09:00",
        "  Sesi 1    09:00–12:00 (Jumat sampai 11:30)",
        "  Istirahat 12:00–13:30 (Jumat 11:30–14:00)",
        "  Sesi 2    13:30–15:50 (Jumat dari 14:00)",
        "  Close     ~16:00–16:15",
        "",
        "Scheduler otomatis (GitHub Actions):",
        "  09:10  mode open   — early volume + potensi naik",
        "  12:05  mode midday — break sesi 1",
        "  16:20  mode eod    — konfirmasi + SL/TP final",
        "",
        "Perbandingan metode:",
        "",
    ]
    for key in ("eod", "open", "midday", "morning"):
        a = ADVICE[key]
        marker = " ← PALING ANDAL" if key == "eod" else ""
        lines.extend(
            [
                f"[{key.upper()}]{marker}",
                f"  Cron WIB : {a.recommended_cron}",
                f"  Tujuan   : {a.purpose}",
                f"  Andalan  : {a.reliability}",
                f"  Cocok utk: {a.best_for}",
                "",
            ]
        )
    lines.extend(
        [
            "Kesimpulan:",
            "  1) 09:10 = early alert (noisy).",
            "  2) 12:05 break sesi 1 = cek volume setengah hari.",
            "  3) 16:20 EOD = keputusan utama + SL/TP.",
        ]
    )
    return "\n".join(lines)
