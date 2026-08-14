Pylon Backup Report for AlmaLinux 8

Version 0.14.3 displays the Active Backup table in the approved DSM Task List
order and renumbers No. for display. Every other value remains unchanged from
the authoritative CSV; unknown tasks append in their original CSV order.

Version 0.14.2 accepts an optional Task List image from clipboard paste or file
selection and places it above the first-page result table. The image is not OCRed
and cannot overwrite CSV values.

Version 0.14.0 removes Active Backup screen automation from report generation.
The primary NAS is used only to download the exact dated CSV through DSM File
Station; both the main table and Check/Audit pages come from that one CSV. No
Synology API is used for the primary NAS. Yard API and Sangfor capture remain.

Version 0.13.6 dismisses DSM's taskbar preview-mask after switching to Active
Backup and hit-tests the selected task row before clicking it.

Version 0.13.5 hit-tests Active Backup with document.elementFromPoint before
declaring it foreground. A DOM-visible File Server menu covered by maximized
File Station no longer produces a false positive.

Version 0.13.4 switches from maximized File Station to Active Backup through
the visible DSM top taskbar and validates the unique File Server navigation.
It no longer relies on ExtJS toFront or the active-win CSS state.

Version 0.13.3 brings the already-open Active Backup ExtJS window to the
foreground before interacting with it. This supports maximized File Station,
which intentionally has no minimize or close title-bar control.

Version 0.13.2 replaces intercepted pointer clicks with verified ExtJS window
actions. It minimizes or closes only the foreground File Station component and
reports the exact attempted method when DSM keeps the window active.

Version 0.13.1 detects a restored maximized File Station active window, cancels
its Settings dialog without saving, and minimizes File Station before clicking
Active Backup Details. Blocked clicks now fail quickly with a diagnostic image.

Version 0.13.0 introduced Web API only for the Yard Drive ShareSync site. Later
versions supersede its primary-NAS Audit capture path; primary NAS never uses
Synology Web API.

Version 0.12.8 dismisses a restored DSM Settings dialog without saving, brings
Active Backup to the foreground, and scopes File Server, task-grid and Details
locators to the Active Backup application window so File Station cannot receive
forced clicks intended for a background application.

Version 0.12.7 accepts Details only after the visible window title matches
Details: <task>, then opens Log only inside that verified window and confirms
the Type, Time and Event log grid.

Version 0.12.6 selects File Server only from the DSM left navigation and
requires all six exact task-grid headers. This prevents the Overview dashboard's
File Server and Last Backup Time widgets from being mistaken for Task List.

Version 0.12.5 selects the owning Active Backup task row before opening Details,
skips hidden duplicate toolbar controls, and falls back to the DSM row
double-click action.

Version 0.12.4 accepts the Active Backup task grid immediately after opening
File Server and only clicks the optional Task List tab when the grid is not
already visible. It validates the real Task Name and Last Backup columns.

Version 0.12.3 fixes DSM hidden-template collisions by choosing an actually
visible text match instead of locator.first. It also adds a live CSV smoke-test
button that downloads and parses today's file without generating a PDF.

Version 0.12.2 locates the visible File Station context-menu Download command
across every DSM frame. The diagnostic confirmed that DSM renders this menu
outside the main page frame even though it is visible on screen.

Version 0.12.1 downloads the selected exact-dated CSV from its File Station
right-click context menu. This avoids DSM's toolbar being rendered outside the
application-window DOM scope on the installed DSM version.

Version 0.12.0 downloads the exact current-day abb_daily_result_YYYY-MM-DD.csv
through the visible File Station UI. Manual upload remains an optional fallback.
No Synology API client is used and no prior-day/latest filename is substituted.

Version 0.11.5 removes every innerText/ancestor-content readiness gate from the
Yard path. The Sync log result is accepted only by before/after visual change;
visible exact locators count status labels independently across DSM frames.

Version 0.11.4 stops relying on the unstable DSM Sync log DOM. It compares the
ShareSync window pixels before and after the verified toolbar click, requires a
material visual change, and saves the post-click image as Yard evidence.

Version 0.11.3 verifies the visible Sync log title and table columns across the
rendered DSM page instead of requiring a specific internal dialog ancestor.
The captured ShareSync application rectangle contains both visible windows.

Version 0.11.2 recognizes the Sync log as a separate DSM dialog and captures
the combined Synced folders and Sync log window area as one Yard evidence image.

Version 0.11.1 opens the verified Drive ShareSync list/Sync-log toolbar button,
requires the Sync log panel to be visible, and captures only the application
window so DSM desktop notifications are excluded from the PDF.

Version 0.11.0 removes direct Synology NAS API access from the production
bundle. The operator uploads abb_daily_result_YYYY-MM-DD.csv manually. Chromium
captures Active Backup Audit and Yard Synced folders/Sync log from the normal
DSM web interface. The bundle includes synology_api.py only for Yard
Drive ShareSync; obsolete api_collector.py is not included.

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
Version 0.8.8 simplifies the daily HCI status wording to "ตรวจสอบหน้า HCI Backup สำเร็จ" while keeping the automatic Latest Backup sort before capture unchanged.
Version 0.9.0 changes the PDF presentation to the approved legacy pattern: Active Backup task list and 15-column result table, one evidence page per Check task, then Yard and Sangfor HCI. Start and End are displayed from the authoritative NAS CSV values. Existing report deletion and cleanup remain limited to generated PDF and paired text files in the report folder and never touch NAS backup data.
Version 0.9.1 preserves each NAS test result when one site fails, so the web UI displays the exact Site error instead of replacing it with a generic error message. Data collection and PDF rules are unchanged.
Version 0.9.2 uses the configured abb_daily_result_latest.csv first. Only when that path returns HTTP 404 does it try the exact abb_daily_result_YYYY-MM-DD.csv for the current report date. It never substitutes a previous day and records the actual source path in the test result and PDF.
Version 0.10.0 replaces that rule: only abb_daily_result_YYYY-MM-DD.csv matching the report date is accepted. Last Backup is displayed as Start, End is never synthesized or displayed, and appended AUDIT blocks are authoritative for Check evidence pages. Missing files, schema changes, row-shape changes, date mismatches and Check/AUDIT mismatches stop report generation and are recorded in seven-day history as source-contract alerts.

1) แตกไฟล์ ZIP แล้วเข้าโฟลเดอร์ที่แตก
2) รัน: chmod +x install.sh && ./install.sh
3) แก้ไฟล์: /etc/backup-report/backup-report.env
4) ตรวจฟอนต์ด้วย: fc-match -f '%{file}\n' 'Noto Sans Thai'
5) ยังไม่ต้องเปิดพอร์ตหรือ Start service จนกว่าจะตรวจค่า configuration ครบ

ตัวติดตั้งไม่แก้ Nginx, MySQL, Zabbix หรือ Firewall
