#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root" >&2
  exit 1
fi

SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

command -v python3.12 >/dev/null || { echo "python3.12 is required" >&2; exit 1; }
id backup-report >/dev/null 2>&1 || useradd --system --home-dir /var/lib/backup-report --shell /sbin/nologin backup-report

install -d -o root -g backup-report -m 0750 /opt/backup-report/app /etc/backup-report
install -d -o backup-report -g backup-report -m 0750 /var/lib/backup-report/data /var/lib/backup-report/reports /var/lib/backup-report/logs /var/lib/backup-report/captures
install -d -o backup-report -g backup-report -m 0700 /var/lib/backup-report/runtime

cp -a "${SOURCE_DIR}/app/." /opt/backup-report/app/
chown -R root:backup-report /opt/backup-report/app
find /opt/backup-report/app -type d -exec chmod 0750 {} +
find /opt/backup-report/app -type f -exec chmod 0640 {} +

python3.12 -m venv /opt/backup-report/venv
/opt/backup-report/venv/bin/python -m pip install --disable-pip-version-check -r "${SOURCE_DIR}/requirements.txt"
chown -R root:backup-report /opt/backup-report/venv
chmod -R g+rX,o-rwx /opt/backup-report/venv

install -o root -g root -m 0644 "${SOURCE_DIR}/backup-report.service" /etc/systemd/system/backup-report.service
if [[ ! -f /etc/backup-report/backup-report.env ]]; then
  install -o root -g backup-report -m 0640 "${SOURCE_DIR}/backup-report.env.example" /etc/backup-report/backup-report.env
fi

ENV_FILE=/etc/backup-report/backup-report.env
ensure_env_default() {
  local key=$1
  local value=$2
  grep -q "^${key}=" "${ENV_FILE}" || printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
}
ensure_env_default BACKUP_REPORT_CAPTURE_ROOT /var/lib/backup-report/captures
ensure_env_default BACKUP_REPORT_CHROMIUM /usr/bin/chromium-browser
ensure_env_default BACKUP_REPORT_CHROMIUM_RUNTIME /var/lib/backup-report/runtime
chown root:backup-report "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

systemctl daemon-reload
echo "Installed. Edit /etc/backup-report/backup-report.env before starting the service."
