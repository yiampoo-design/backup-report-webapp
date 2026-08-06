# Architecture

## Components

### `app.py`

HTTP server, session authentication, settings API, report history and orchestration. Runtime paths are controlled with `BACKUP_REPORT_*` environment variables.

### `synology_api.py`

DSM authentication, API discovery and authenticated requests. Sessions and SynoToken values remain in memory and are cleared on logout.

### `api_collector.py`

Normalizes responses from Active Backup and Cloud Sync into the report model. Report generation fails closed when required source data cannot be read.

### `sangfor_capture.py`

Starts the system Chromium through Playwright, logs into aCloud, opens the configured VM Backup route, waits for the backup table and writes a 1920x1080 PNG.

### `build_backup_report.py`

Builds an A4 landscape PDF with ReportLab:

1. Daily overview
2. Data integrity and audit table
3. One detail page for every task requiring `Check`
4. Sangfor VM Backup evidence as the final page when enabled

## Data flow

1. An authenticated team member requests a report.
2. Saved settings are merged with any submitted values.
3. Both Synology sources are collected and normalized.
4. Sangfor is captured when enabled.
5. ReportLab generates the final PDF only after all required sources succeed.
6. The report is listed in the seven-day history.

## Runtime directories on Linux

| Path | Purpose |
|---|---|
| `/opt/backup-report/app` | Read-only application code |
| `/etc/backup-report/backup-report.env` | Service configuration |
| `/var/lib/backup-report/data` | Settings and authentication data |
| `/var/lib/backup-report/reports` | Generated PDF reports |
| `/var/lib/backup-report/captures` | Sangfor screenshots |
| `/var/lib/backup-report/logs` | Sanitized probes and error logs |
| `/var/lib/backup-report/runtime` | Chromium runtime directory |
