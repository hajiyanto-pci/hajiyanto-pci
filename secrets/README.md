# Google Calendar credentials (local only)

Folder ini **tidak di-commit** (lihat `.gitignore`).

## Setup cepat

1. Buka [Google Cloud Console](https://console.cloud.google.com/)
2. Buat/ pilih project → enable **Google Calendar API**
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
4. Download JSON → simpan sebagai:
   - `secrets/credentials.json`
5. Install deps & authorize sekali:
   ```bash
   pip install -r requirements-timesheet.txt
   python3 scripts/google_calendar_auth.py
   ```
6. Browser akan minta login Google kamu; setelah setuju, muncul `secrets/token.json`.

## Generate timesheet + calendar

```bash
python3 scripts/weekly_timesheet.py \
  --git-home /home/haji/git \
  --days 7 \
  --timezone Asia/Jakarta \
  --max-line-hours 2 \
  --calendar \
  --calendar-map config/calendar-project-map.json \
  -o reports/timesheet-latest.md \
  --csv reports/timesheet-latest.csv
```

Salin `config/calendar-project-map.example.json` → `config/calendar-project-map.json` lalu sesuaikan keyword → project.
