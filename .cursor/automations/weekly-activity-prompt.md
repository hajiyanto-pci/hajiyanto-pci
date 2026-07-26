# Automation: Weekly Timesheet (activity → timesheet)

Salin prompt di bawah ke [Cursor Automations](https://cursor.com/automations).

## Setup yang disarankan
- **Trigger:** Scheduled — setiap Senin 09:00 (`0 9 * * 1`) timezone Asia/Jakarta
- **Repository / environment:** yang punya akses ke workspace git kamu  
  Local/WSL path: `/home/haji/git` (`Ubuntu-22.04\home\haji\git`)
- **Tools:** MCP `cursor-cloud`, optional Send to Slack
- **PR creation:** on jika ingin menyimpan `reports/timesheet-*.md` tiap minggu

## Prompt

```text
Kamu adalah Weekly Timesheet Agent.

Periode: 7 hari terakhir (tampilkan jam Asia/Jakarta).
Source git home: /home/haji/git (Windows/WSL: Ubuntu-22.04\home\haji\git). Scan semua project/workspace di bawahnya.

Tugas:
1) Cek aktivitas: commit, push, PR, plus prompt cloud agent (MCP cursor-cloud).
2) Buat timesheet profesional dikelompokkan per project/workspace.
3) Deskripsi tiap line detail dan agak panjang (formal), menyebut tujuan kerja, artefak, dan bukti.
4) HARD RULE: maksimum 2.0 jam per timesheet line. Sesi lebih panjang wajib di-breakdown menjadi beberapa line ≤ 2 jam.

Langkah:
1. Jalankan:
   python3 scripts/weekly_timesheet.py --git-home /home/haji/git --days 7 --timezone Asia/Jakarta --max-line-hours 2 -o reports/timesheet-latest.md --csv reports/timesheet-latest.csv
   python3 scripts/weekly_timesheet.py --git-home /home/haji/git --days 7 --format json -o reports/timesheet-latest.json
   Jika /home/haji/git tidak ada, pakai fallback script dan catat path aktual.
2. list-cloud-agents (created_after=7d, include_archived=true) + batch-fetch-details (diff metadata; transcripts via subagent bila perlu). Map ke project.
3. Enrich deskripsi agar profesional/panjang; pecah ulang bila ada line > 2 jam.
4. Simpan reports/timesheet-YYYY-MM-DD.md, update latest files, commit + draft PR ringkas. Jika tidak ada aktivitas, balas ringkas tanpa PR.
5. Jangan bocorkan secret/token.
```
