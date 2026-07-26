# hajiyanto-pci

## Weekly Timesheet Agent (+ Google Calendar)

Cek aktivitas seminggu (prompt, commit, push, PR, **meeting Google Calendar**) lalu buat timesheet profesional.

### Path workspace git
- Linux/WSL: `/home/haji/git`
- Windows: `Ubuntu-22.04\home\haji\git`

### Aturan timesheet
- Kelompok per project/workspace
- Deskripsi detail & agak panjang
- **Max 2 jam / line** (otomatis di-breakdown)
- Meeting calendar masuk sebagai baris `source=calendar`
- Estimasi coding git dikurangi jika overlap meeting

### Google Calendar setup (sekali)
Lihat `secrets/README.md`, lalu:

```bash
pip install -r requirements-timesheet.txt
# simpan OAuth Desktop client sebagai secrets/credentials.json
python3 scripts/google_calendar_auth.py
cp config/calendar-project-map.example.json config/calendar-project-map.json
```

### Generate timesheet

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

Di Cursor: command **`buat-timesheet-mingguan`**.

| File | Fungsi |
|---|---|
| `.cursor/commands/buat-timesheet-mingguan.md` | Command utama |
| `scripts/weekly_timesheet.py` | Generator timesheet |
| `scripts/google_calendar.py` | Fetch Google Calendar / JSON / ICS |
| `scripts/google_calendar_auth.py` | Login OAuth sekali |
| `config/calendar-project-map.example.json` | Mapping keyword meeting → project |
| `fixtures/sample-calendar-week.json` | Sample calendar untuk uji offline |
