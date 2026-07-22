# Stock Screener IDX — Volume + Break Resistance + Notifikasi

Alat screening saham BEI (IDX) untuk membantu menemukan kandidat yang **berpotensi naik** berdasarkan:

1. **Volume spike** — volume hari ini jauh di atas rata-rata
2. **Break resistance** — harga menutup di atas resistance (high N hari terakhir)
3. **Kualitas momentum** — RSI belum overbought + harga di atas MA

Hasil ditampilkan di terminal, disimpan ke JSON, dan bisa dikirim ke **Telegram**.

> Catatan: ini alat bantu analisis teknikal, **bukan jaminan** saham akan naik. Selalu kombinasikan dengan riset fundamental & manajemen risiko.

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

1. Chat `@BotFather` → buat bot → salin **token**
2. Chat bot-mu, lalu dapatkan **chat_id** (mis. via `@userinfobot`)
3. Isi di `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

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

## Menjalankan screening

```bash
# Scan default (mode EOD / sore)
python run_screener.py

# Mode spesifik
python run_screener.py --mode eod
python run_screener.py --mode morning
python run_screener.py --mode midday

# Scan saham tertentu
python run_screener.py -s BBCA BBRI TLKM ADRO GOTO

# Perketat kriteria
python run_screener.py --volume-spike 2.0 --min-score 70

# Tanpa Telegram
python run_screener.py --no-telegram
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
