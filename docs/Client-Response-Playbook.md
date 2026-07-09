# How We Should Respond — Client Reply Playbook

**Audience:** Internal (Portcities / project team)  
**Purpose:** How to answer the client’s 5 migration questions without over-promising, while sounding clear and in control.

---

## Positioning (tone & strategy)

| Do | Don’t |
|----|--------|
| Sound structured and confident | Give a fixed go-live date before discovery |
| Separate **platform move** from **version upgrade** | Bundle “move to SH + upgrade Odoo” as one cutover |
| Commit to a **method** (staging dry-run → cutover) | Commit to “zero downtime” |
| Ask for access / inventory as the next step | Ask for a blank cheque of credentials with no plan |
| Flag e-invoice as a **must-test** item | Say “e-invoice will just work” without knowing the module |
| Offer a short discovery → then firm estimate | Invent week counts or commercial numbers now |

**One-line stance to use:**

> We can migrate production to Odoo.sh safely with a same-version dump/import, after we validate the codebase and e-invoice flow on a staging copy. Next step is a short discovery so we can lock downtime and effort.

---

## How to answer each of their 5 points

### 1. Database migration

**Say:**
- Best approach = **same Odoo major version**, full backup **with filestore**, import to Odoo.sh after custom modules are in GitHub.
- We will dry-run on **staging** first; production cutover only after UAT sign-off.
- Full history (transactions, attachments, accounting) moves with the dump.

**Don’t say yet:**
- Exact dump duration / freeze length (needs DB + filestore size).

### 2. Codebase & third-party (e-invoice)

**Say:**
- All custom + third-party code must be in the Odoo.sh GitHub repo before import.
- We will run a compatibility check against Odoo.sh limits (no OS packages, cron limits, known risky apps).
- For e-invoice: we need the **exact module name(s)**. Official `l10n_id_efaktur` / Coretax XML export is usually fine; custom API connectors need extra validation (API keys, IP allowlist, submission cron).

**Don’t say yet:**
- “Fully compatible” until we see the installed module list.

### 3. Timeline & downtime

**Say:**
- Work is phased: discovery → repo/SH setup → staging import → UAT → short maintenance window → hypercare.
- Downtime is limited to the **final cutover** (freeze → dump → import → DNS). Users keep working on ERS until that window.
- We minimize downtime by rehearsing once on staging and pre-deploying code.

**Don’t say yet:**
- A calendar end date or “X days total” unless commercial already agreed a band.
- “Near-zero downtime” unless dump is proven small in rehearsal.

**If they push for a number:** give a **conditional** answer, e.g.  
> After discovery and one timed rehearsal we will confirm the maintenance window. For a same-version move, downtime is typically a planned off-peak window measured in hours, driven mainly by database/filestore size—not days of outage.

### 4. Resource requirements

**Say:** we need a clear, limited list (frame as “to start discovery”), not everything on day one:

**Minimum to start:**
1. Odoo version  
2. SSH or DB-manager access (read-only OK first)  
3. Installed modules export / Apps list  
4. DB + filestore approximate size  
5. E-invoice module technical name  
6. GitHub + Odoo Enterprise/Odoo.sh subscription owner  
7. DNS contact for cutover later  

**Later (before cutover):** integration credentials, mail/DNS, UAT owners, maintenance window approval.

### 5. Risk management

**Say:**
- Main risks: missing/incompatible modules, e-invoice/compliance break, mail/integrations, insufficient storage for import.
- Controls: staging rehearsal, go/no-go checklist, keep ERS as rollback until hypercare ends, do not upgrade version in the same cutover.

This reassures them you are not underestimating compliance (especially tax invoicing).

---

## Recommended response structure

Use this order in email / meeting:

1. **Acknowledge** the goal (ERS → Odoo.sh production).  
2. **Recommend approach** in 3–4 bullets (same version, Git first, staging dry-run, short freeze).  
3. **Answer the 5 points** briefly (or attach the analysis doc).  
4. **Call out e-invoice** as a focus item.  
5. **Ask for discovery inputs** (checklist).  
6. **Propose next meeting** (discovery / access handoff), not go-live.

---

## Draft reply (English — ready to send / adapt)

Subject: ERS → Odoo.sh migration — approach & next steps

Hi [Name],

Thank you for the clear questions. Below is how we recommend approaching the move from the dedicated ERS server to Odoo.sh.

**Recommended approach**  
We propose a **same Odoo version** migration: place all custom and third-party modules in the GitHub repository linked to Odoo.sh, restore a full database backup (including filestore) onto an Odoo.sh **staging** environment, complete UAT, then cut over production in a controlled maintenance window. We recommend treating any Odoo **version upgrade** as a separate project after the platform move is stable.

**1. Database migration**  
Best path is a full backup with filestore from ERS, imported into Odoo.sh after the codebase is deployed. Transaction history and attachments move with that backup. We will validate the restore on staging before touching production.

**2. Codebase & third-party addons (incl. e-invoice)**  
We will inventory and back up the current codebase into the Odoo.sh repository and check compatibility with Odoo.sh constraints (dependencies, scheduled jobs, known incompatible patterns).  
For e-invoice specifically: official Indonesia e-Faktur / Coretax export modules are generally supported on Odoo.sh; if you use a **custom or partner API connector**, we need to validate API credentials, submission jobs, and any IP allowlisting. Please share the technical name of the e-invoice module(s) in use so we can assess this precisely.

**3. Timeline & downtime**  
Work is phased (discovery → repository/Odoo.sh setup → staging restore → UAT → cutover → hypercare). User-facing downtime is limited to the final cutover window. We minimize it by rehearsing the restore on staging and switching DNS only after smoke checks. Exact window length depends mainly on database and filestore size; we will confirm it after discovery and a timed rehearsal.

**4. What we need from you to start**  
- Current Odoo version  
- Access for discovery (SSH and/or database manager; read-only is fine initially)  
- List of installed apps/modules and approximate DB + filestore size  
- E-invoice module name(s) and any other critical integrations (payment, banking, etc.)  
- GitHub ownership and Odoo Enterprise subscription that includes Odoo.sh  
- DNS contact for the production domain (needed before cutover)

**5. Risks & how we manage them**  
Main risks are missing or incompatible modules, e-invoice/compliance issues after the move, mail/integration reconfiguration, and import storage sizing. We mitigate these with a staging dry-run, a go/no-go checklist, selective re-enablement of scheduled actions after import, and keeping the ERS environment available as rollback until hypercare is complete.

If this approach works for you, we suggest a short discovery call / access handoff next so we can lock the cutover window and a firm delivery plan.

Best regards,  
[Your name]

---

## Draft reply (Bahasa Indonesia — jika komunikasi internal/client ID)

Subject: Migrasi ERS → Odoo.sh — pendekatan & next steps

Halo [Nama],

Terima kasih atas poin-poinnya. Ringkasnya, kami sarankan migrasi **versi Odoo yang sama**: kode custom & third-party masuk GitHub Odoo.sh, restore database + filestore ke **staging**, UAT, baru cutover production di maintenance window. Upgrade versi Odoo sebaiknya dipisah setelah platform stabil.

1. **Database** — dump lengkap + filestore; history ikut pindah; staging dulu sebelum production.  
2. **Codebase / e-invoice** — audit kompatibilitas Odoo.sh; untuk e-invoice kami perlu nama teknis modul (official e-Faktur/Coretax vs connector API custom).  
3. **Timeline / downtime** — downtime hanya di cutover; lama window dikunci setelah discovery + rehearsal (terutama ukuran DB/filestore).  
4. **Kebutuhan akses** — versi Odoo, akses discovery, daftar modul, ukuran DB, modul e-invoice, GitHub + subscription Odoo.sh, kontak DNS.  
5. **Risiko** — modul hilang/incompatible, e-invoice, mail/integrasi, storage; mitigasi: staging dry-run, go/no-go, ERS tetap sebagai rollback sampai hypercare selesai.

Next step yang kami usulkan: sesi discovery singkat + penyerahan akses.

Terima kasih,  
[Nama]

---

## Insights — what “good” looks like in this reply

1. **You lead with method, not dates.** Clients asking these 5 points usually want reassurance that you have a playbook.  
2. **Split platform vs upgrade.** Stops scope creep and protects the downtime promise.  
3. **Make e-invoice visible.** Shows you understand ID compliance risk; builds trust.  
4. **Turn “resources needed” into a short checklist.** Easier for the client to action than a vague “we need access.”  
5. **Name rollback explicitly.** Reduces fear of a one-way cutover.  
6. **Close with a next step you control** (discovery call), not “we’ll migrate next month.”

---

## Optional commercial / scoping note (internal only)

After Phase 0, convert to a fixed proposal with:
- In-scope: same-version move, staging, UAT support, cutover, hypercare (define days)
- Out-of-scope / optional: major version upgrade, rewriting incompatible apps, new Coretax API if missing, performance tuning beyond worker sizing
- Assumptions: module list complete, no undocumented server-side daemons, client provides UAT sign-off

Do **not** put commercial numbers in the first analytical reply unless sales already aligned.
