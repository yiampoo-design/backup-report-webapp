# Architecture

## Components

### `app.py`

HTTP server, session authentication, settings API, report history and orchestration. Runtime paths are controlled with `BACKUP_REPORT_*` environment variables.

### `csv_report.py`

Validates and parses the exact daily CSV downloaded through File Station or
uploaded explicitly as a fallback. It has no
network client and does not import any Synology API module.

### `synology_web_capture.py`

Starts system Chromium through Playwright, logs into the normal DSM web UI and
downloads the exact dated CSV through File Station. The primary NAS path does
not issue direct NAS API calls. DSM's own browser page may use its normal
internal requests while rendering.

### `yard_api.py` and `synology_api.py`

Dedicated Yard-only client for Drive ShareSync Connection, Session and sync
history. It is never passed the primary NAS configuration and contains no
Active Backup or File Station API names.

### `sangfor_capture.py`

Starts the system Chromium through Playwright, logs into aCloud, opens the configured VM Backup route, waits for the backup table and writes a 1920x1080 PNG.

### `build_backup_report.py`

Builds an A4 landscape PDF with ReportLab:

1. Optional operator-supplied Task List image followed by the authoritative
   14-column Active Backup table from the exact dated CSV (`Last Backup`
   displayed as `Start`; no synthesized `End`)
2. One CSV `AUDIT` detail page for every task requiring `Check` or a
   non-success status
3. Yard / Drive ShareSync API table
4. Sangfor VM Backup evidence as the final page

There is no separate Data Integrity summary page. See `REPORT_SPEC.md` for the
approved page and field contract.

## Data flow

1. An authenticated team member requests a report.
2. Saved settings are merged with any submitted values.
3. Chromium downloads the exact current-date CSV through File Station. If the
   operator selected a manual fallback, that exact file is used instead. Its
   rows and AUDIT blocks are parsed without recalculating fields.
4. CSV `AUDIT` blocks supply the conditional detail pages, the dedicated Yard
   API reads Drive ShareSync, and Sangfor is captured when enabled.
5. ReportLab generates the final PDF only after all required sources succeed.
6. The report is listed in the seven-day history.

## Runtime directories on Linux

| Path | Purpose |
|---|---|
| `/opt/backup-report/app` | Read-only application code |
| `/etc/backup-report/backup-report.env` | Service configuration |
| `/var/lib/backup-report/data` | Settings and authentication data |
| `/var/lib/backup-report/reports` | Generated PDF reports |
| `/var/lib/backup-report/captures` | DSM and Sangfor screenshots |
| `/var/lib/backup-report/logs` | Source-contract alerts and error logs |
| `/var/lib/backup-report/runtime` | Chromium runtime directory |
