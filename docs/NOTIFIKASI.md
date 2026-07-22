# Panduan Notifikasi Telegram & WhatsApp

Agar kamu menerima alert saham yang:
- volume naik
- harga di atas MA
- sedang akumulasi
- break resistance

isi kredensial di file `.env`, lalu jalankan screener.

## 1) Setup Telegram (disarankan, paling mudah)

1. Buka Telegram, chat **@BotFather**
2. Kirim `/newbot` → ikuti instruksi → salin **token** bot
3. Chat bot yang baru dibuat (kirim `/start`)
4. Dapatkan **chat_id**:
   - cara cepat: chat **@userinfobot** → salin Id, atau
   - buka: `https://api.telegram.org/bot<TOKEN>/getUpdates` setelah kamu chat bot
5. Isi `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:AA...token...
TELEGRAM_CHAT_ID=987654321
```

6. Uji:

```bash
python run_screener.py --test-notify
```

## 2) Setup WhatsApp via CallMeBot (gratis, pribadi)

CallMeBot mengirim WA ke nomormu sendiri.

1. Simpan kontak WhatsApp CallMeBot: **+34 644 66 78 60**
2. Kirim pesan ke nomor itu:
   `I allow callmebot to send me messages`
3. Bot membalas dengan **API key**
4. Isi `.env` (nomor internasional tanpa `+` juga boleh):

```env
WHATSAPP_PHONE=62812xxxxxxx
CALLMEBOT_APIKEY=123456
```

5. Uji:

```bash
python run_screener.py --test-notify
```

> Catatan: CallMeBot untuk pemakaian pribadi. Jangan share API key.

## 3) WhatsApp via Twilio (opsional, berbayar/sandbox)

Jika butuh lebih formal:

```env
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=xxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_TO=whatsapp:+62812xxxxxxx
```

Screener memakai CallMeBot dulu; jika kosong, baru coba Twilio.

## 4) Jalankan screening + kirim notifikasi

```bash
# Scan sore (rekomendasi) lalu kirim ke Telegram/WA
python run_screener.py --mode eod

# Hanya uji koneksi notifikasi
python run_screener.py --test-notify

# Nonaktifkan salah satu channel sementara
python run_screener.py --no-telegram
python run_screener.py --no-whatsapp
```

## 5) Contoh isi pesan yang kamu terima

```
Stock Screener IDX — EOD Confirmed (sore)
Waktu: 2026-07-22 16:20
Ditemukan: 3 saham kandidat naik

CUAN | skor 93 | harga 735
✅ Volume 3.5x
✅ Di atas MA (690)
✅ Akumulasi
✅ Break resistance (690, +6.5%)
```

## 6) Jadwal otomatis (cron, WIB)

```cron
20 16 * * 1-5 cd /path/ke/repo && .venv/bin/python run_screener.py --mode eod >> logs/screener.log 2>&1
```

Pastikan file `.env` ada di folder yang sama saat cron jalan.
