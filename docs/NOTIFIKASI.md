# Panduan Notifikasi Telegram & WhatsApp

Agar kamu menerima alert saham yang:
- volume naik
- harga di atas MA
- sedang akumulasi
- break resistance

isi kredensial di file `.env`, lalu jalankan screener.

## 1) Setup Telegram (disarankan, paling mudah)

### A. Buat bot + token
1. Buka Telegram, chat **@BotFather**
2. Kirim `/newbot` → ikuti instruksi → salin **token** bot

### B. Ambil chat_id (dari awal)
Chat ID **baru muncul setelah kamu menekan Start** di bot.

1. Buka bot kamu, contoh: https://t.me/Sahamgacor_bot
2. Tekan **Start** atau kirim `/start`
3. Di komputer/repo, jalankan:

```bash
python run_screener.py --get-chat-id --token "ISI_TOKEN_BOT_DISINI" --save-env
```

Perintah itu akan menunggu, lalu menampilkan `chat_id` dan menyimpannya ke `.env`.

**Cara manual (tanpa script):**
1. Setelah `/start` di bot, buka di browser:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
2. Cari angka di `"chat":{"id": 123456789` → itu `chat_id`-mu

### C. Isi `.env`
```env
TELEGRAM_BOT_TOKEN=123456789:AA...token...
TELEGRAM_CHAT_ID=987654321
```

### D. Uji kirim
```bash
python run_screener.py --test-notify
```

> Keamanan: jangan kirim token bot ke orang lain / chat publik.
> Jika token sudah terekspos, di @BotFather kirim `/revoke` lalu buat token baru.

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
