# Pylon Backup Report

Current Linux release: 0.14.3. The primary NAS path contains no Synology API
client. Chromium downloads the exact `abb_daily_result_YYYY-MM-DD.csv`
for the report date through the normal File Station UI; an operator upload is
available as an explicit fallback. Every main-table value is
read from that file; `Last Backup` is displayed as `Start` and `End` is not
displayed. The optional Task List image is supplied by the operator, while each
Audit detail page is built from the appended `AUDIT` section in the same CSV.
Yard Drive ShareSync is read through its dedicated Web API module. If the exact
CSV or its contract cannot be verified, report generation stops.

เว็บแอปภายในสำหรับสร้างรายงาน PDF จากระบบสำรองข้อมูลหลายแหล่ง โดยไม่พึ่ง Map Drive, SMB, WebDAV หรือการ Export CSV ด้วยมือ

## ความสามารถ

- ดาวน์โหลด `abb_daily_result_YYYY-MM-DD.csv` อัตโนมัติผ่านหน้า File Station หรืออัปโหลดด้วยมือเป็น fallback
- วางภาพ Task List จาก Clipboard ด้วย Ctrl+V หรือเลือกไฟล์ เพื่อแสดงเหนือข้อมูล CSV ในหน้าแรก
- เรียงแถวตาราง CSV และเลข No. ให้ตรงกับ Task List ที่แสดงด้านบน โดยไม่แก้ค่าข้อมูลจาก CSV
- สร้างหน้า Audit จากส่วน `AUDIT` ท้าย CSV เดียวกัน หนึ่งหน้าต่อรายการ `Check`
- อ่าน Yard Drive ShareSync ผ่าน Web API เฉพาะ NAS Yard
- Login เข้า Sangfor aCloud ด้วย Headless Chromium และ Capture หน้า VM Backup
- สร้าง PDF แบบ A4 แนวนอน ประกอบด้วยภาพรวม ตาราง Audit หน้ารายละเอียดต่อรายการ `Check` และหลักฐาน Sangfor ท้ายรายงาน
- Login/Logout สำหรับทีมและเปลี่ยนรหัสผ่านผ่านหน้าเว็บ
- บันทึกการตั้งค่าและบัญชีระบบต้นทางไว้บน Server
- พับช่อง Username/Password อัตโนมัติหลังบันทึก เพื่อลดการแก้ไขโดยไม่ตั้งใจ
- แสดงรายงานย้อนหลัง 7 วัน

## สถาปัตยกรรม

```text
Team Browser
    |
    v
Pylon Backup Report (Python, port 8780)
    |-- File Station Chromium -> Exact dated CSV (manual fallback)
    |-- Appended CSV AUDIT ----> One detail page per Check
    |-- Yard Web API ----------> Drive ShareSync folders / sync history
    |-- Headless Chromium -----> Sangfor aCloud
    `-- ReportLab -------------> PDF + 7-day history
```

รายละเอียดเพิ่มเติม:

- [Architecture](docs/ARCHITECTURE.md)
- [Claude Code instructions](CLAUDE.md)
- [Project handoff (Thai)](docs/HANDOFF_TH.md)
- [Claude Code starting prompt (Thai)](docs/CLAUDE_START_PROMPT_TH.md)
- [Approved report specification](docs/REPORT_SPEC.md)
- [Approved v0.14.3 baseline](docs/APPROVED_BASELINE_V0.14.3.md)
- [Linux deployment](docs/DEPLOYMENT.md)
- [Operations and troubleshooting](docs/OPERATIONS.md)
- [Security notes](docs/SECURITY.md)

## เริ่มแบบ Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python app.py
```

โหมด Windows แบบ local จะ bind ที่ `127.0.0.1` และใช้ URL token ชั่วคราว ส่วน Linux service ใช้ระบบ session login

## สร้าง Linux bundle

```powershell
.\build_linux_bundle.ps1
```

ผลลัพธ์อยู่ใต้ `output/linux/` และไม่ควร commit ZIP หรือข้อมูล runtime เข้า repository

## ข้อมูลที่ไม่อยู่ใน Git

`.gitignore` ป้องกัน credentials, settings, logs, diagnostics, captures, reports, CSV และ build artifacts ค่า URL ใน source เป็นเพียงตัวอย่าง ผู้ดูแลต้องกำหนดค่าจริงผ่านหน้าเว็บหรือไฟล์ environment บน Server

## สถานะ

เวอร์ชันปัจจุบัน: `0.14.3-task-list-order`
