# Linux deployment

Target used during development: AlmaLinux 8, Python 3.12, systemd and Chromium.

## Prerequisites

```bash
python3.12 --version
chromium-browser --version
```

Thai fonts are required for PDF output. Set the exact regular and bold font paths in the environment file.

## Install or upgrade

Extract a Linux bundle, then run:

```bash
chmod +x install.sh
systemctl stop backup-report
./install.sh
systemctl start backup-report
```

The installer preserves an existing `/etc/backup-report/backup-report.env` and appends new runtime keys when an upgrade introduces them. Data under `/var/lib/backup-report` is preserved.

## Verify

```bash
systemctl status backup-report --no-pager -l
curl -sS http://127.0.0.1:8780/health
```

Open only the required firewall scope. For an internal subnet example:

```bash
firewall-cmd --zone=public \
  --add-rich-rule='rule family="ipv4" source address="10.0.0.0/24" port protocol="tcp" port="8780" accept'
```

Use the network range approved by the organization; do not copy the example blindly.

## Upgrade note

Application code under `/opt` is read-only under the systemd hardening policy. Every generated file must be directed to `/var/lib/backup-report` through the environment variables in `backup-report.env`.
