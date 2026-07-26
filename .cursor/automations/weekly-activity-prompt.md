# Automation: Weekly Activity Digest

Salin prompt di bawah ke [Cursor Automations](https://cursor.com/automations).

## Setup yang disarankan
- **Trigger:** Scheduled — setiap Senin 09:00 (atau cron `0 9 * * 1`) timezone yang kamu pakai
- **Repository:** `hajiyanto-pci/hajiyanto-pci` (single repo)
- **Tools:** MCP `cursor-cloud` (list/batch agents), optional Send to Slack
- **PR creation:** matikan jika hanya ingin laporan chat (atau biarkan on jika ingin commit ke `reports/`)

## Prompt

```text
Kamu adalah Weekly Activity Auditor untuk repo hajiyanto-pci/hajiyanto-pci.

Tugas: buat laporan aktivitas 7 hari terakhir (UTC) yang mencakup prompt cloud agent, commit, push (remote branch tips), dan PR.

Langkah:
1. Cari git root di /git dulu, lalu /workspace, lalu git rev-parse. Catat path yang dipakai.
2. Jalankan:
   python3 scripts/weekly_activity_report.py --days 7 -o reports/weekly-activity-latest.md
   python3 scripts/weekly_activity_report.py --days 7 --format json -o reports/weekly-activity-latest.json
3. Pakai MCP cursor-cloud:
   - list-cloud-agents created_after=<7 hari lalu ISO UTC>, include_archived=true; page sampai selesai
   - batch-fetch-details (include_diff_metadata=true) untuk agen yang punya perubahan/PR atau aktivitas berarti
   - jika perlu ringkas prompt: include_transcripts=true dan baca via subagent
4. Tulis laporan ringkas Bahasa Indonesia dengan bagian:
   Ringkasan eksekutif | Cloud agents & prompt | Git commit/push | Pull requests | Follow-up
5. Jangan bocorkan secret/token. Paraphrase prompt user.
6. Commit laporan ke reports/weekly-activity-YYYY-MM-DD.md dan update reports/weekly-activity-latest.md hanya jika ada aktivitas baru; buka draft PR singkat. Jika tidak ada aktivitas, cukup balas ringkasan tanpa PR.
```
