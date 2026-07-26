# hajiyanto-pci

## Weekly Activity Agent

Alat untuk cek aktivitas seminggu (prompt cloud agent, commit, push, PR).

| File | Fungsi |
|---|---|
| `.cursor/commands/cek-aktivitas-mingguan.md` | Command/prompt agent di Cursor |
| `.cursor/automations/weekly-activity-prompt.md` | Prompt siap tempel ke [Automations](https://cursor.com/automations) (jadwal mingguan) |
| `scripts/weekly_activity_report.py` | Collector dari `.git` (+ `gh` untuk PR) |
| `reports/` | Output laporan |

### Cek cepat (git/PR)

```bash
python3 scripts/weekly_activity_report.py --days 7
```

Script mencari git root di `/git`, lalu `/workspace`, lalu cwd. Di cloud agent saat ini repo ada di `/workspace` (folder `/git` tidak selalu ada).
