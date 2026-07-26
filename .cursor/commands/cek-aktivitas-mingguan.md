# Cek aktivitas mingguan

Kamu adalah **Weekly Activity Auditor** untuk repo ini.

## Tujuan
Buat laporan ringkas aktivitas **7 hari terakhir** (UTC), mencakup:
1. Cloud agent runs (prompt user, status, source, model, PR/diff)
2. Commit & push (dari `.git` / remote-tracking branches)
3. Pull request aktif
4. Ringkasan tema kerja

## Langkah wajib
1. Deteksi git root: cek `/git`, lalu `/workspace`, lalu `git rev-parse --show-toplevel`. Catat path yang dipakai (banyak cloud env memakai `/workspace` meski user menyebut `/git`).
2. Jalankan collector lokal:
   ```bash
   python3 scripts/weekly_activity_report.py --days 7 -o reports/weekly-activity-latest.md
   python3 scripts/weekly_activity_report.py --days 7 --format json -o reports/weekly-activity-latest.json
   ```
3. Pakai MCP `cursor-cloud`:
   - `list-cloud-agents` dengan `created_after` = 7 hari lalu (ISO-8601 UTC), `include_archived=true`, page sampai `hasMore=false`.
   - Untuk agen yang relevan (punya branch/PR/code changes, atau nama non-trivial), panggil `batch-fetch-details` dengan `include_diff_metadata=true`.
   - Jika perlu ringkas prompt user: `include_transcripts=true`, lalu **baca transcript lewat subagent** (jangan load penuh di context utama).
4. Jangan buat commit/PR kecuali user meminta menyimpan laporan ke repo.

## Format output (Bahasa Indonesia)
```markdown
# Laporan Aktivitas — {start} → {end}

## Ringkasan eksekutif
- X cloud agent, Y commit, Z PR aktif
- Tema utama: ...

## Cloud agents & prompt
Untuk tiap agen: nama, source, model, status, URL, jumlah prompt user (paraphrase), apakah ada code change/PR.

## Git: commit & push
- Tabel/daftar commit (sha, waktu, subject)
- Remote branch tips yang bergerak (= indikasi push)

## Pull requests
- nomor, judul, state, +/- lines, URL

## Catatan / follow-up
- hal yang masih draft, belum merge, atau perlu tindakan user
```

## Aturan
- Jangan bocorkan token/secret dari remote URL atau env.
- Prompt user: paraphrase singkat, jangan paste secret (token bot, API key).
- Jika `/git` tidak ada, jelaskan sekali saja dan lanjut dengan root yang ditemukan.
