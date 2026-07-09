# ERS Dedicated Server → Odoo.sh Migration Analysis

**Prepared for:** Client production migration planning  
**Context:** Move production from dedicated ERS hosting to Odoo.sh  
**Date:** 9 July 2026  
**Status:** Pre-engagement analysis (discovery still required for final estimates)

---

## Executive summary

Migrating from a dedicated ERS server to Odoo.sh is a **same-version dump-and-restore** project when the Odoo major version stays unchanged. Success depends less on infrastructure and more on:

1. Getting **all custom + third-party modules** into a GitHub repository that Odoo.sh can build.
2. Validating **compatibility** with Odoo.sh constraints (no system packages, cron timeouts, mail ports, known incompatible addons).
3. Running a **staging dry-run** before production cutover.
4. Planning a short, controlled freeze window for the final dump → import → DNS switch.

**Recommended approach:** keep the same Odoo major version for go-live; treat any version upgrade as a separate project after the platform move is stable.

---

## 1. Database migration — recommended approach

### 1.1 Best-practice path (same major version)

| Step | Action |
|------|--------|
| A | Inventory installed modules, DB size, filestore size, Odoo version, PostgreSQL version |
| B | Create / connect GitHub repo; push all custom & third-party addons |
| C | Create Odoo.sh project on the **same major Odoo version** as production |
| D | Deploy code to a **staging** branch and confirm build succeeds |
| E | Take a full backup from ERS: **ZIP with filestore** (`/web/database/manager` or `pg_dump` + filestore archive) |
| F | Import dump into Odoo.sh **staging** (Backups → Import Database) |
| G | Re-enable required crons selectively; fix mail, integrations, e-invoice |
| H | UAT / regression on staging |
| I | Production cutover: freeze writes → final dump → import to production branch → DNS / subscription register |

Official Odoo.sh import rules that matter:

- Dump must be the **same major Odoo version** as the Odoo.sh project (no cross-version import).
- Import needs roughly **4× dump size** free storage temporarily (e.g. 10 GB dump → ≥ 40 GB available).
- After import, **outgoing mail servers are disabled** and **scheduled actions are disabled** by design.
- Import **overwrites** the target branch database.

### 1.2 What moves with the dump

| Included | Notes |
|----------|--------|
| Business data & history | Partners, orders, invoices, stock moves, accounting, chatter, etc. |
| Filestore | Attachments, PDF reports, product images — must use backup **with filestore** |
| Module install state | Modules marked installed in DB must exist in the Git repo at restore time |
| Config / parameters | System parameters, users, access rights |

| Not automatic / must reconfigure | Notes |
|----------------------------------|--------|
| Custom SMTP | Prefer Odoo.sh default mail, or external SMTP on **465/587** (port 25 closed) |
| Crons | Re-enable only what is needed after import |
| Enterprise subscription link | Unlink old DB, register new Odoo.sh DB |
| DNS / custom domain | Point domain to Odoo.sh after cutover |
| IP allowlists / firewall rules | Odoo.sh outbound IP can change; plan for integrations |
| SSH / OS-level cron / custom daemons | Not available on Odoo.sh — must be redesigned |

### 1.3 Custom modules & data history

- **Code** lives in GitHub (Odoo.sh builds from branches).
- **Data history** lives in the PostgreSQL dump + filestore.
- Push modules **before** importing the dump. If a module is installed in DB but missing from the repo, the build/import will fail or features will break.
- Public community modules: prefer **Git submodules**.
- Private repos: add Odoo.sh **deploy keys** for submodules.

### 1.4 If a version upgrade is also desired

Do **not** combine platform move + major upgrade in one cutover unless forced.

1. Migrate ERS → Odoo.sh on **current** version.  
2. Stabilize.  
3. Upgrade via Odoo’s upgrade service / OpenUpgrade path on Odoo.sh later.

Custom module schemas and business logic are **not** upgraded automatically; they need migration scripts (`migrations/` pre/post) and testing.

---

## 2. Codebase & third-party addons (incl. e-invoice)

### 2.1 Repository backup & structure

Ensure the current ERS codebase is fully under Git (not only on the server disk):

```text
repo/
├── custom/                 # client-specific modules
├── third_party/            # purchased / partner apps (or git submodules)
├── requirements.txt        # Python deps (pip only; no apt)
└── .gitmodules             # if using submodules
```

Odoo.sh auto-detects addon folders via `__manifest__.py`.

**Actions before go-live:**

1. Full `git` inventory of `/opt/.../addons` (or equivalent) on ERS.
2. Compare with `ir_module_module` where `state = 'installed'`.
3. Resolve orphans: installed in DB but missing from Git.
4. Commit licenses / purchase credentials for paid apps where needed.
5. Add `requirements.txt` for any Python libraries used by custom code.

### 2.2 Odoo.sh compatibility checklist

| Constraint | Impact |
|------------|--------|
| No OS package install (`apt`) | Modules needing native libs / binaries may fail |
| Python deps via `requirements.txt` only | Must be pip-installable |
| Cron execution time limits | Long jobs must be batched; recurrent timeouts → cron auto-disabled |
| Known incompatible / risky modules | e.g. `queue_job` (AUP / performance), `odoo_agent` (longpolling) |
| No persistent custom system daemons | Background workers outside Odoo workers are not supported |
| Staging = 1 worker; limited cron | Heavy UAT load tests are constrained |
| Mail port 25 closed | Use 465/587 or Odoo.sh mail |

### 2.3 E-invoice module (Indonesia) — specific assessment

“E-invoice” in ID projects usually means one of:

| Type | Typical modules | Odoo.sh fit |
|------|-----------------|-------------|
| Official Odoo e-Faktur CSV | `l10n_id_efaktur` (Enterprise) | Compatible — export CSV for legacy DJP desktop flow |
| Official Coretax XML | `l10n_id_efaktur_coretax` | Compatible — generates XML for Coretax upload |
| Partner / custom Coretax API connector | Custom third-party | Compatible **if** pure Python + HTTPS APIs; verify secrets, webhooks, IP allowlisting |
| Non-ID e-invoicing (Peppol, etc.) | Country EDI modules | Usually OK; Odoo.sh may strip some EDI tokens — re-test |

**What to verify for the client’s e-invoice module:**

1. Exact technical name(s) and whether Enterprise localization or custom partner app.
2. Does it call DJP/Coretax **API** or only generate **file export**?
3. Any dependency on local desktop tools, Windows paths, or OS packages?
4. Stored certificates / API keys / NPWP / PKP partner flags after restore.
5. Cron jobs that submit invoices — timeout and retry behavior on Odoo.sh.
6. Whether Coretax/DJP side allowlists the **source IP** (Odoo.sh IPs can change; use notification hooks if required).
7. Post-migration test: create invoice → generate e-Faktur/Coretax file or API submit → confirm acceptance.

**Recommendation:** treat e-invoice as a **P0 UAT scenario**. Do not cut over production until at least one full tax-invoice cycle succeeds on staging with a copy of production data.

### 2.4 Other third-party apps to flag early

- Payment gateways, banking sync, shipping connectors  
- Document management / S3 / Nextcloud bridges  
- WhatsApp / SMS / telephony  
- BI extractors, middleware, ESB  
- Anything using `queue_job`, Redis, or external workers  

---

## 3. Timeline & downtime (how to minimize)

> Durations below are **engineering effort bands**, not calendar commitments. Final schedule depends on DB size, module count, and e-invoice complexity discovered in Phase 0.

### 3.1 Phased plan

| Phase | Scope | Effort band | Downtime? |
|-------|--------|-------------|-----------|
| **0. Discovery** | Version, DB/filestore size, module list, integrations, e-invoice type, access | Short | No |
| **1. Repo & Odoo.sh setup** | GitHub cleanup, Odoo.sh project, branches, workers/storage sizing | Short–medium | No |
| **2. Code compatibility** | Fix SH-incompatible code, `requirements.txt`, submodule keys | Medium (varies with custom code) | No |
| **3. Staging import dry-run** | Full dump → staging import → fix mail/crons/integrations | Medium | No (prod stays up) |
| **4. UAT** | Business + e-invoice + accounting + inventory scenarios | Medium | No |
| **5. Cutover** | Freeze → final dump → prod import → DNS → smoke test | Short window | **Yes — planned** |
| **6. Hypercare** | Monitor, re-enable remaining crons, support | Short | No |

### 3.2 Minimizing downtime

**Target cutover pattern (same version):**

1. Announce maintenance window (prefer low-traffic hours).
2. Put ERS in **read-only / freeze** (block new transactions; or stop HTTP and warn users).
3. Take **final** dump with filestore.
4. Import to Odoo.sh **production** branch.
5. Spot-check: login, open SO/invoice, attachment, e-invoice generate, mail.
6. Switch DNS / custom domain to Odoo.sh.
7. Register Enterprise subscription on the new DB; unlink old.
8. Re-enable production crons carefully.
9. Keep ERS offline but retained as rollback for an agreed period.

**Downtime drivers:**

| Factor | Effect |
|--------|--------|
| Dump size / upload bandwidth | Dominates freeze length |
| Filestore size | Large attachments slow backup & import |
| Failed module load | Extends window if not caught in staging |
| DNS TTL | Lower TTL 24–48h before cutover |

**Typical freeze window (indicative):** from under an hour for small DBs with rehearsed runbook, to several hours for large filestores — **only measurable after Phase 0 sizing and one staging rehearsal**.

**Ways to shrink the window:**

- Rehearse cutover once on staging with a production-sized dump and time each step.
- Pre-upload code; only data moves at cutover.
- Pre-configure domain on Odoo.sh; only flip DNS at the end.
- Lower DNS TTL in advance.
- Do **not** upgrade Odoo version during cutover.

---

## 4. Resource requirements (access & prerequisites)

### 4.1 From the client / ERS side

| Item | Why needed |
|------|------------|
| Odoo **major version** + build/commit if customized | Must match Odoo.sh project |
| Master password / DB manager access **or** SSH + `pg_dump` + filestore path | To produce valid backup |
| SSH / server access to ERS (read-only OK for discovery) | Module inventory, sizes, cron, nginx, custom services |
| List of custom domains & DNS admin access | Cutover |
| Odoo Enterprise **subscription code** with Odoo.sh hosting | Project creation / production |
| GitHub org access (or approve new repo + Odoo.sh GitHub App) | Code hosting |
| Inventory of third-party apps + licenses | Legal & technical deploy |
| SMTP / email DNS (SPF/DKIM) owner | Mail deliverability on SH |
| Integration credentials (payment, DJP/Coretax, banks, APIs) | Re-test after move |
| Sample e-invoice test NPWP / sandbox if available | Safe UAT |
| Business UAT owners (Finance, Ops, Sales) | Sign-off |
| Approximate DB + filestore size | Storage planning (4× rule) |
| Current backup policy & RPO/RTO expectations | Rollback design |
| Any IP allowlists on partner systems | Update for Odoo.sh egress |

### 4.2 From Portcities / implementer side

| Item | Why |
|------|-----|
| Odoo.sh project admin | Import, branches, logs, shells |
| Ability to increase **storage** temporarily for import | 4× dump size |
| Extra **staging** branch if parallel workstreams | Isolation |
| Extra **workers** if production concurrency requires it | Performance |
| Runbook for cutover & rollback | Execution |

### 4.3 Prerequisites before kickoff

- [ ] Confirmed target: **same version** move vs move+upgrade  
- [ ] GitHub repository ready and Odoo.sh authorized  
- [ ] Subscription includes Odoo.sh (not Online-only)  
- [ ] Hosting region chosen (latency for ID users)  
- [ ] Maintenance window agreed with business  
- [ ] Rollback retention period for ERS server agreed  

---

## 5. Risk management

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Custom/third-party module incompatible with Odoo.sh | Medium | High | Compatibility audit in Phase 2; replace/refactor before cutover |
| Missing module in Git vs installed in DB | Medium | High | Diff `ir_module_module` vs repo; staging import rehearsal |
| E-invoice / Coretax failure after move | Medium | High (compliance) | P0 UAT; verify API vs file flow; IP/DNS/secrets; keep ERS rollback |
| Dump too large / storage insufficient | Medium | High | Measure size early; temporarily raise SH storage (≥4×) |
| Long cron jobs killed / disabled on SH | Medium | Medium | Batch jobs; monitor; redesign queue_job-style workers |
| Mail not sending / spam | Medium | Medium | Use SH mail or 465/587; fix SPF/DKIM; test after import |
| Integration IP allowlist breaks | Low–Medium | High | Document egress; update partners; use SH IP-change hooks |
| Data loss / incomplete filestore | Low | Critical | Always backup **with filestore**; checksum; open sample attachments in UAT |
| Users keep writing to ERS during cutover | Medium | High | Freeze + communication; optionally stop service before final dump |
| Combining version upgrade with move | — | Critical | Split projects; same-version move first |
| Subscription / duplicate DB blocking | Medium | Medium | Unlink old DB; register new; one production DB per subscription |
| Performance regression (workers/resources) | Medium | Medium | Size workers from ERS concurrency; monitor post-go-live |
| Rollback needed | Low | High | Keep ERS intact + final pre-cutover dump; DNS revert plan |

### 5.1 Rollback strategy

1. Do not decommission ERS until hypercare ends.  
2. Keep the pre-cutover dump offline.  
3. If Odoo.sh production fails critically: revert DNS to ERS, investigate on SH staging.  
4. Define a clear “go / no-go” checklist before DNS flip.

### 5.2 Go / no-go checklist (production)

- [ ] Staging import succeeded with production-like dump  
- [ ] All installed modules present and load without error  
- [ ] Finance: invoice, payment, tax report  
- [ ] E-invoice: generate + accept (file or API)  
- [ ] Stock / sales / purchase smoke tests  
- [ ] Attachments open  
- [ ] Mail test  
- [ ] Critical crons identified and re-enable plan ready  
- [ ] DNS TTL lowered; domain ready on SH  
- [ ] Subscription registration steps documented  
- [ ] Rollback owner and contact list confirmed  

---

## Recommended next actions (to start)

1. **Discovery workshop (Phase 0)** — collect version, sizes, module list, e-invoice technical names, integrations.  
2. **Code freeze into GitHub** — full backup of custom + third-party addons.  
3. **Odoo.sh project creation** on matching version + staging dry-run import.  
4. **E-invoice deep-dive** — confirm CSV vs Coretax XML vs API connector.  
5. **Agree cutover window** only after one timed rehearsal.

---

## Appendix A — Official references

- [Create an Odoo.sh project / import database](https://www.odoo.com/documentation/master/administration/odoo_sh/getting_started/create.html)  
- [Odoo.sh FAQ](https://www.odoo.sh/faq)  
- [Indonesia localization / e-Faktur / Coretax](https://www.odoo.com/documentation/19.0/applications/finance/fiscal_localizations/indonesia.html)  

## Appendix B — Information still needed from client

Please provide (or grant access to collect):

1. Current Odoo version (e.g. 16.0 / 17.0 / 18.0)  
2. Database size and filestore size  
3. Export of installed modules (`Apps` filter Installed, or SQL on `ir_module_module`)  
4. Technical name of the e-invoice module(s)  
5. List of payment / shipping / EDI / middleware integrations  
6. Whether any `queue_job` or custom background workers are in use  
7. Preferred Odoo.sh region and target go-live constraints  
8. GitHub ownership (client org vs Portcities)  

---

*This document is an analysis and planning baseline. Final effort, downtime, and commercial estimate require Phase 0 discovery against the live ERS environment.*
