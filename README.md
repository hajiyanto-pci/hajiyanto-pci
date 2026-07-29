# Stock Screener IDX — Multi-faktor + Notifikasi Online

Alat screening saham BEI untuk menemukan kandidat berpotensi naik dengan:

1. Volume spike  
2. Break resistance  
3. Di atas MA  
4. Akumulasi OBV  
5. Stochastic  
6. Money-flow / proksi bandarmology (CMF + MFI)  
7. MACD + RSI  

Hasil ke **Telegram/WhatsApp**, bisa dijalankan **online via GitHub Actions** (tanpa clone tiap hari).

- Panduan online vs lokal: [`docs/ONLINE.md`](docs/ONLINE.md)  
- Formula skor: [`docs/FORMULA.md`](docs/FORMULA.md)  
- Setup notifikasi: [`docs/NOTIFIKASI.md`](docs/NOTIFIKASI.md)  

> Catatan: ini alat bantu teknikal, **bukan jaminan** saham akan naik.

## Chat ke bot Telegram

Setelah `python run_bot.py` berjalan (atau Cloud Agent online), chat `@Sahamgacor_bot`.

Bot memakai **agent mode**: pahami dulu maksud chat → konfirmasi singkat → jalankan tool analisa.

```
dapatkah cek potensi ihsg
analisa fundamental saham BBCA
please cek roe pbv BBRI
cek saham bandarmology hari ini
tolong cek saham teknikal stochastic yang lagi bagus
cek saham teknikal stochastic potensi naik
/teknikal
please cek saham emtk
/watch EMTK
/help
```

Opsional NLU lebih bebas: set `OPENAI_API_KEY` di `.env` (lihat `.env.example`).

## Cara kerja skor

Setiap saham yang lolos filter dapat skor 0–100:

| Komponen | Bobot | Keterangan |
|----------|------:|------------|
| Volume spike | 35 | Semakin tinggi vs rata-rata, semakin baik |
| Kekuatan breakout | 30 | Seberapa jauh di atas resistance |
| RSI | 20 | Ideal di zona 50–65 |
| Harga vs MA | 15 | Tren naik jika di atas MA |

Default: hanya saham dengan **skor ≥ 60** yang masuk alert.

## Instalasi lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Lebih praktis:** jalankan online via GitHub Actions — lihat [`docs/ONLINE.md`](docs/ONLINE.md).

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
