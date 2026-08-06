# Operations and troubleshooting

## Daily use

1. Login to the internal web app.
2. Confirm all saved-source indicators are present.
3. Use the individual test buttons after a source password or URL changes.
4. Run Sangfor test capture and inspect its preview after aCloud UI upgrades.
5. Generate the PDF and check the seven-day history.

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
