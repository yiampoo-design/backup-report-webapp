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
Version 0.8.2 cross-checks task name, status and latest result time against Active Backup Web API. Differences are reported as warnings and never overwrite the authoritative NAS CSV values.
Version 0.8.3 serializes the Active Backup API cross-check timestamp before returning the web response, fixing "Object of type datetime is not JSON serializable" after report generation.
Version 0.8.4 places each Active Backup Check detail page before Yard and renders Yard Synced folders beside an equal number of newest Sync log events on one page.
Version 0.8.5 removes the repetitive Data Integrity page. Check detail pages are inserted only when Check items exist, before Yard and Sangfor; source and API cross-check status remain in the first-page subtitle.
Version 0.8.6 creates an editable daily message beside the PDF, adds one-click Copy in the web UI and saves the same message as a UTF-8 text file.
Version 0.8.7 displays each daily message inside the 7-day report history with a Copy button, so the team can review and reuse past status summaries without locating text files.

1) แตกไฟล์ ZIP แล้วเข้าโฟลเดอร์ที่แตก
2) รัน: chmod +x install.sh && ./install.sh
3) แก้ไฟล์: /etc/backup-report/backup-report.env
4) ตรวจฟอนต์ด้วย: fc-match -f '%{file}\n' 'Noto Sans Thai'
5) ยังไม่ต้องเปิดพอร์ตหรือ Start service จนกว่าจะตรวจค่า configuration ครบ

ตัวติดตั้งไม่แก้ Nginx, MySQL, Zabbix หรือ Firewall
