# Operations and troubleshooting

## Daily use

1. Login to the internal web app.
2. Confirm all saved-source indicators are present.
3. Use the individual test buttons after a source password or URL changes.
4. Run Sangfor test capture and inspect its preview after aCloud UI upgrades.
5. Generate the final PDF at or after 09:00 Asia/Bangkok and check the seven-day history.

## Daily 09:00 report window

- The final daily window is 00:00-09:00 Asia/Bangkok for the current calendar date.
- A report generated before 09:00 is explicitly labelled `Pre-09:00 draft`; its cutoff is the actual collection time.
- A report generated after 09:00 keeps the 09:00 cutoff so the report is reproducible for the scheduled delivery.
- Active Backup rows, timestamps and audit fields come only from the
  NAS-generated `abb_daily_result_YYYY-MM-DD.csv` matching the report date.
  The appended `AUDIT` blocks are the evidence source. The app must not use a
  previous date, synthesize a missing row or reconstruct an `End` time.
- No Active Backup API call is allowed. Yard Drive ShareSync is the only NAS API
  scope and never replaces any primary-NAS CSV value.
- Rows are displayed in the approved DSM Task List order and `No.` is
  renumbered. All other values remain unchanged. Unknown tasks append in their
  original CSV order.
- The optional Task List image is pasted or selected by the operator. It is
  presentation evidence only and is never OCRed or used to overwrite CSV data.

## Sangfor capture order

Before every Sangfor test or report capture, the app reads the visible `Latest Backup` timestamps and clicks the column header until the values are newest-to-oldest. Capture stops with an error instead of attaching an unverified order when no backup timestamps are visible or the sort cannot be confirmed.

## Health checks

```bash
curl -sS http://127.0.0.1:8780/health
ss -lntp '( sport = :8780 )'
journalctl -u backup-report -n 100 --no-pager -o cat
```

## Common failures

### Connection refused

The service is stopped or exited before binding the port. Check `systemctl status` and `journalctl` before changing firewall rules.

### Read-only filesystem under `/opt`

An output environment variable is absent. Verify that data, reports, logs, captures and Chromium runtime paths point to `/var/lib/backup-report`.

### Sangfor login succeeds manually but capture fails

- Confirm the service user can start `/usr/bin/chromium-browser`.
- Confirm the aCloud URL and VM Backup hash route.
- Leave certificate verification disabled only for an internally approved self-signed certificate.
- Re-test selectors after an aCloud UI upgrade.

### PDF Thai or Latin text is missing

Confirm both configured font files contain Thai and Latin glyphs. Garuda regular/bold was used successfully during the AlmaLinux validation.

## Password recovery

If the web password is forgotten, stop the service, set a temporary initial password in the protected environment file, remove only `web_auth.json`, then start the service. This intentionally resets web authentication and must be performed by an authorized root administrator.
