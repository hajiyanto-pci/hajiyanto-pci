# hajiyanto-pci

## Weekly Timesheet / Activity Agent

Agent AI untuk cek aktivitas seminggu (prompt, commit, push, PR) dan membuat **timesheet profesional**.

### Path workspace git
- Linux/WSL: `/home/haji/git`
- Notasi Windows: `Ubuntu-22.04\home\haji\git`

Tiap repo di bawah folder itu = satu project pada timesheet.

### Fitur timesheet
- Dikelompokkan per project/workspace
- Deskripsi detail & agak panjang (profesional)
- **Maksimum 2 jam per line** — sesi lebih panjang di-breakdown otomatis

| File | Fungsi |
|---|---|
| `.cursor/commands/buat-timesheet-mingguan.md` | Command utama: buat timesheet |
| `.cursor/commands/cek-aktivitas-mingguan.md` | Cek aktivitas (+ arahkan ke timesheet) |
| `.cursor/automations/weekly-activity-prompt.md` | Prompt Automations jadwal mingguan |
| `scripts/weekly_timesheet.py` | Generator timesheet multi-repo |
| `scripts/weekly_activity_report.py` | Collector aktivitas single-repo |
| `reports/` | Output laporan & timesheet |

### Pakai cepat

```bash
# Di mesin Ubuntu/WSL kamu:
python3 scripts/weekly_timesheet.py \
  --git-home /home/haji/git \
  --days 7 \
  --timezone Asia/Jakarta \
  --max-line-hours 2 \
  -o reports/timesheet-latest.md \
  --csv reports/timesheet-latest.csv
```

Di Cursor: jalankan command **buat-timesheet-mingguan**.
