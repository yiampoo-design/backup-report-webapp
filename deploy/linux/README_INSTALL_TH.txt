Pylon Backup Report for AlmaLinux 8

Version 0.6 adds a Login page, Logout, and Change Password in the Account menu.
The username and password in backup-report.env create the initial account only.
After first start, the password is stored as a PBKDF2 hash at:
/var/lib/backup-report/data/web_auth.json

Version 0.7 adds automatic Sangfor aCloud login and VM Backup screenshot capture.
It uses the existing /usr/bin/chromium-browser and appends the capture to the PDF.
Version 0.7.1 automatically folds saved source credentials in the team UI.
Version 0.7.3 adds the Pylon logo and application name to every PDF page header.
Version 0.7.4 starts the PDF download automatically after report generation.
Version 0.7.5 aligns Check with NAS status, uses a 7-day comparison window and adds a Yard/Cloud Sync report page.
Version 0.7.6 uses a daily 00:00-09:00 Asia/Bangkok NAS API window, labels pre-09:00 drafts and reports missing current-window tasks without substituting old results.
Version 0.7.7 verifies that Sangfor Latest Backup is sorted newest-to-oldest before every test and report capture.
Version 0.8.0 reads Yard status from Synology Drive ShareSync Connection, Session and sync-history APIs, matching DSM's Synced folders page.
Version 0.8.1 downloads /ABB_Backup/ABB_Report/abb_daily_result_latest.csv through Synology FileStation Web API and uses it as the authoritative Active Backup report source. Same Size, Audit Window and Audit Status are no longer recalculated by the web app.

1) แตกไฟล์ ZIP แล้วเข้าโฟลเดอร์ที่แตก
2) รัน: chmod +x install.sh && ./install.sh
3) แก้ไฟล์: /etc/backup-report/backup-report.env
4) ตรวจฟอนต์ด้วย: fc-match -f '%{file}\n' 'Noto Sans Thai'
5) ยังไม่ต้องเปิดพอร์ตหรือ Start service จนกว่าจะตรวจค่า configuration ครบ

ตัวติดตั้งไม่แก้ Nginx, MySQL, Zabbix หรือ Firewall
