# Stock Screener IDX — Volume + Break Resistance + Notifikasi

Alat screening saham BEI (IDX) untuk membantu menemukan kandidat yang **berpotensi naik** berdasarkan:

1. **Volume spike** — volume hari ini jauh di atas rata-rata
2. **Di atas MA** — harga close di atas moving average
3. **Akumulasi** — OBV naik + volume beli dominan
4. **Break resistance** — harga menutup di atas resistance (high N hari terakhir)

Hasil ditampilkan di terminal, disimpan ke JSON, dan bisa dikirim ke **Telegram** serta **WhatsApp**.

> Catatan: ini alat bantu analisis teknikal, **bukan jaminan** saham akan naik. Selalu kombinasikan dengan riset fundamental & manajemen risiko.

## Notifikasi Telegram / WhatsApp

Panduan lengkap: [`docs/NOTIFIKASI.md`](docs/NOTIFIKASI.md)

```bash
cp .env.example .env
# isi TELEGRAM_* dan/atau WHATSAPP_PHONE + CALLMEBOT_APIKEY
python run_screener.py --setup-notify   # tampilkan panduan
python run_screener.py --test-notify    # uji kirim pesan
python run_screener.py --mode eod       # scan + kirim alert
```

## Cara kerja skor

Setiap saham yang lolos filter dapat skor 0–100:

| Komponen | Bobot | Keterangan |
|----------|------:|------------|
| Volume spike | 35 | Semakin tinggi vs rata-rata, semakin baik |
| Kekuatan breakout | 30 | Seberapa jauh di atas resistance |
| RSI | 20 | Ideal di zona 50–65 |
| Harga vs MA | 15 | Tren naik jika di atas MA |

Default: hanya saham dengan **skor ≥ 60** yang masuk alert.

## Instalasi

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Notifikasi Telegram (opsional)

Lihat panduan langkah demi langkah: [`docs/NOTIFIKASI.md`](docs/NOTIFIKASI.md)

Ringkas:
1. Telegram: `@BotFather` → token + chat_id
2. WhatsApp: CallMeBot → `WHATSAPP_PHONE` + `CALLMEBOT_APIKEY`
3. Uji: `python run_screener.py --test-notify`

## Kapan notifikasi paling cocok?

| Waktu | Mode | Cocok? | Keterangan |
|-------|------|:------:|------------|
| **Sore ~16:20** | `eod` | **Ya (utama)** | Close & volume sudah final → sinyal paling andal |
| Pagi ~08:30 | `morning` | Opsional | Watchlist dari breakout kemarin untuk siap di open |
| Siang 11:00/14:00 | `midday` | Opsional | Early alert volume naik; lebih banyak noise |

Lihat penjelasan lengkap:

```bash
python run_screener.py --explain-schedule
```

## Analisa hari kemarin

```bash
# Sesi bursa sebelumnya (lewati Sabtu/Minggu)
python run_screener.py --as-of kemarin

# Tanggal spesifik
python run_screener.py --as-of 2026-07-21

# Tanpa Telegram
python run_screener.py --as-of kemarin --no-telegram
```

Hasil JSON tersimpan di `output/signals_latest.json` (EOD) / `signals_latest_<mode>.json`.

## Jadwalkan otomatis (cron, TZ=Asia/Jakarta)

```cron
# UTAMA: sore setelah close
20 16 * * 1-5 cd /path/ke/hajiyanto-pci && .venv/bin/python run_screener.py --mode eod >> logs/screener.log 2>&1

# Opsional: pagi watchlist
30 8 * * 1-5 cd /path/ke/hajiyanto-pci && .venv/bin/python run_screener.py --mode morning >> logs/screener.log 2>&1

# Opsional: early alert siang
0 11,14 * * 1-5 cd /path/ke/hajiyanto-pci && .venv/bin/python run_screener.py --mode midday >> logs/screener.log 2>&1
```

## Ubah kriteria

Edit `config.yaml`:

- `volume_spike_min` — minimal kelipatan volume (default `1.5`)
- `resistance_lookback` — window resistance (default `20` hari)
- `rsi_max` — batasi overbought (default `75`)
- `min_score` — ambang alert (default `60`)
- `symbols` — daftar saham custom (kosong = pakai default likuid)

## Struktur

```
run_screener.py          # entrypoint
config.yaml              # kriteria screening
screener/
  data.py                # ambil data Yahoo Finance
  indicators.py          # RSI, MA, resistance
  signals.py             # filter + skor
  schedule.py            # rekomendasi jadwal pagi/siang/sore
  notifier.py            # console / JSON / Telegram
  universe.py            # daftar saham IDX default
```
