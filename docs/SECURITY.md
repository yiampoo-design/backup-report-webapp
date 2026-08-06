# Security notes

## Web authentication

- Passwords are stored as PBKDF2-SHA256 hashes.
- Sessions use HttpOnly and SameSite cookies.
- State-changing requests require a session CSRF token.
- Password changes revoke all active sessions.

## Source-system credentials

- Password values are never returned to the browser after saving.
- DSM session IDs, SynoToken values and submitted passwords are redacted from diagnostic output.
- Windows uses DPAPI tied to the saving user.
- The current Linux credential store relies primarily on restrictive filesystem permissions. Treat `/var/lib/backup-report/data` as sensitive and restrict root/backup-report access.

## Network transport

HTTP Basic or session authentication over plain HTTP does not provide transport encryption. Deploy behind an approved HTTPS reverse proxy or use a trusted internal network/VPN before expanding access.

## Repository hygiene

Never commit:

- `backup-report.env`
- `settings.json` or `web_auth.json`
- reports, screenshots or CSV exports
- diagnostic files or logs
- real internal/public infrastructure addresses
