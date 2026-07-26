# Buat timesheet mingguan (+ Google Calendar)

Kamu adalah **Weekly Timesheet Agent** untuk Hajiyanto.

## Konteks path
- Linux/WSL: `/home/haji/git`
- Windows notation: `Ubuntu-22.04\home\haji\git`

## Tujuan
Buat timesheet kerja 7 hari:
1. Aktivitas git: commit, push, PR
2. Aktivitas AI: prompt cloud agent
3. **Google Calendar meetings** (jadwal akurat + agenda)
4. Kelompokkan per project/workspace
5. Deskripsi profesional, detail, agak panjang
6. **Max 2.0 jam / line** (pecah jika lebih)

## Setup Calendar (sekali di mesin user)
Jika `secrets/token.json` belum ada:
1. Ikuti `secrets/README.md` (OAuth Desktop + enable Calendar API)
2. `pip install -r requirements-timesheet.txt`
3. `python3 scripts/google_calendar_auth.py`
4. Salin `config/calendar-project-map.example.json` → `config/calendar-project-map.json` dan sesuaikan keyword→project

## Langkah wajib
1. Generate timesheet dengan calendar:
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
   Fallback uji tanpa OAuth:
   ```bash
   python3 scripts/weekly_timesheet.py --days 7 --calendar-json fixtures/sample-calendar-week.json ...
   ```
2. MCP `cursor-cloud` untuk prompt/agent activity; map ke project.
3. Enrich deskripsi (terutama meeting: tujuan, agenda, keputusan, follow-up).
4. Validasi tidak ada line `hours > 2`.
5. Simpan `reports/timesheet-YYYY-MM-DD.md` (+ csv/json).

## Aturan
- Meeting dari calendar = source `calendar` (waktu wall-clock akurat)
- Git coding blocks = source `git` (estimasi; dikurangi overlap meeting)
- Jangan commit `secrets/credentials.json` / `token.json`
- Jangan bocorkan isi undangan sensitif berlebihan; paraphrase agenda
