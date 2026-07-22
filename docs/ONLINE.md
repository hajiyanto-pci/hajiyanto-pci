# Cara Menjalankan: Online vs Lokal

## Opsi 1 — Online otomatis (disarankan, tanpa clone tiap hari)

Pakai **GitHub Actions** di repo ini:

1. Merge/push kode ke GitHub
2. Buka repo → **Settings → Secrets and variables → Actions → New repository secret**
3. Tambahkan secret:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - (opsional) `WHATSAPP_PHONE`, `CALLMEBOT_APIKEY`
4. Buka tab **Actions → Stock Screener IDX (online)**
5. Klik **Run workflow** (manual) atau biarkan cron tiap hari kerja **16:20 WIB**

Workflow file: `.github/workflows/screener.yml`

Manual dengan tanggal kemarin:
- di UI Actions isi `as_of` = `kemarin` atau `2026-07-21`

> Kamu **tidak perlu** menyalakan laptop. GitHub yang menjalankan script dan mengirim Telegram.

## Opsi 2 — Lokal (clone)

```bash
git clone https://github.com/hajiyanto-pci/hajiyanto-pci.git
cd hajiyanto-pci
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# isi TELEGRAM_* di .env
python run_screener.py --as-of kemarin
```

## Opsi 3 — Cloud agent / VPS

Jalankan cron di VPS/Raspberry Pi/Cloud Agent Cursor dengan perintah yang sama seperti lokal.

## Mana yang dipilih?

| Kebutuhan | Pilihan |
|-----------|---------|
| Notifikasi harian otomatis | **GitHub Actions (online)** |
| Eksperimen formula / debug | Lokal |
| Analisa ad-hoc tanggal tertentu | Lokal atau Actions manual |
