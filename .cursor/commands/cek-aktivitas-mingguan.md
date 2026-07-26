# Cek aktivitas mingguan

Kamu adalah **Weekly Activity Auditor**. Untuk **timesheet profesional (max 2 jam/line)**, utamakan command `buat-timesheet-mingguan`.

## Tujuan
Buat laporan ringkas aktivitas **7 hari terakhir**, lalu tawarkan/hasilkan timesheet.

Source git home:
- `/home/haji/git` (Ubuntu-22.04\\home\\haji\\git)
- fallback: `/git`, `/workspace`, atau root yang ditemukan script

## Langkah
1. Activity raw:
   ```bash
   python3 scripts/weekly_activity_report.py --days 7 -o reports/weekly-activity-latest.md
   ```
2. Timesheet (per project, max 2h/line):
   ```bash
   python3 scripts/weekly_timesheet.py --git-home /home/haji/git --days 7 --timezone Asia/Jakarta --max-line-hours 2 -o reports/timesheet-latest.md --csv reports/timesheet-latest.csv
   ```
3. MCP `cursor-cloud`: list agents 7 hari + detail/diff; ringkas prompt user via subagent bila perlu.
4. Output Indonesia untuk ringkasan; deskripsi timesheet profesional & panjang; **tidak ada line > 2 jam**.

## Aturan
- Jangan bocorkan secret/token.
- Jika `/home/haji/git` tidak ada, sebutkan sekali dan lanjut dengan fallback.
