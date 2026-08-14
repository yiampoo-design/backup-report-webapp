# Claude Code project instructions

Read this file, `README.md`, `docs/HANDOFF_TH.md`,
`docs/APPROVED_BASELINE_V0.14.3.md`, and `docs/REPORT_SPEC.md` before proposing
or making changes.

## Non-negotiable data contract

- The authoritative Active Backup report source is
  `/ABB_Backup/ABB_Report/abb_daily_result_YYYY-MM-DD.csv` matching the report
  date, downloaded from the primary NAS through the visible File Station UI.
  Never request `latest`, use a previous day's file, or synthesize a missing row.
  Record the resolved path in the test result and PDF.
- Preserve every NAS CSV value. Never recompute, infer, replace, or "correct"
  `Last Backup`, `Same Size`, `Audit Same Size`, or `Audit Status`. Display
  `Last Backup` as `Start`; do not reconstruct or display `End`.
- Never call a Synology Web API on the primary NAS. Chromium may use the visible
  File Station UI only to download the dated CSV. Active Backup Audit detail
  pages come from the appended `AUDIT` section of that CSV. Synology Web API is
  permitted only for the Yard Drive ShareSync site.
- If a report requirement is ambiguous, stop and ask the owner. Do not invent a
  layout, business rule, status, missing row, or fallback value.

## Approved PDF contract

The six historical PDFs supplied outside Git are the visual and presentation
reference. The required page order is:

1. Active Backup page: optional operator-supplied Task List image followed by
   the exact 14-column NAS result table documented in `docs/REPORT_SPEC.md`.
2. One evidence page for each row whose `Audit Status` is `Check`, or whose
   backup status is not successful. Omit these pages when no row qualifies.
3. Yard / Drive ShareSync page.
4. Sangfor HCI screenshot, last.

Do not restore the removed duplicate "Data Integrity and Audit Details" page.
Dates use the Thai Buddhist calendar where specified. `Start` must show the
full CSV `Last Backup` datetime as `DD/MM/YYYY HH:MM:SS`. `End` is prohibited.
Rows are displayed in the approved DSM Task List order and `No.` is renumbered;
all other field values remain authoritative CSV values. Unknown tasks append in
their original CSV order.

## Source-specific rules

- Yard uses `SYNO.SynologyDriveShareSync.Connection` and
  `SYNO.SynologyDriveShareSync.Session`. Show the folder list in the NAS order,
  and align an equal number of newest log events beside it for comparison.
- Sangfor uses headless Chromium. Confirm that `Latest Backup` is sorted
  newest-to-oldest before capturing; fail rather than attach an unverified
  ordering.

## Safety and repository hygiene

- Never commit or print passwords, session tokens, saved settings, NAS CSVs,
  customer PDFs, captures, logs, diagnostics, or runtime data.
- Do not connect to production systems unless the owner explicitly authorizes
  it for the current task. Prefer fixtures, fakes, and temporary directories.
- Report cleanup may delete only generated PDF files and their paired TXT
  summaries inside the configured report directory. It must never touch a NAS
  backup or any other Zabbix data.
- The installer must not change Zabbix, nginx, MySQL, or firewall settings.

## Runtime and release process

Production currently targets AlmaLinux 8 with systemd and listens on port 8780:

- code: `/opt/backup-report/app`
- environment: `/etc/backup-report/backup-report.env`
- mutable state: `/var/lib/backup-report`
- reports: `/var/lib/backup-report/reports`
- service: `backup-report`

For a release, update the version consistently in `app.py`, `README.md`,
`build_linux_bundle.ps1`, and `deploy/linux/README_INSTALL_TH.txt`. Then:

1. Run Python compilation checks and `git diff --check`.
2. Build the Linux bundle and verify ZIP integrity and SHA-256.
3. Generate a representative PDF, render every page with Poppler, and inspect
   every rendered page.
4. Programmatically compare every CSV `Last Backup` value with PDF `Start`,
   verify that `End` is absent, and validate Check/AUDIT block matching.
5. State exactly what was tested and any test-data limitation.

Do not commit directly until the diff and validation results have been reviewed.
