# Pylon Backup Report

เว็บแอปภายในสำหรับสร้างรายงาน PDF จากระบบสำรองข้อมูลหลายแหล่ง โดยไม่พึ่ง Map Drive, SMB, WebDAV หรือการ Export CSV ด้วยมือ

## ความสามารถ

- ดึงสถานะงานจาก Synology Active Backup for Business ผ่าน DSM Web API
- ดึงสถานะ Synology Cloud Sync ผ่าน DSM Web API
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
    |-- Synology DSM Web API --> Active Backup
    |-- Synology DSM Web API --> Cloud Sync
    |-- Headless Chromium ----> Sangfor aCloud
    `-- ReportLab ------------> PDF + 7-day history
```

รายละเอียดเพิ่มเติม:

- [Architecture](docs/ARCHITECTURE.md)
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

เวอร์ชันปัจจุบัน: `0.7.8-all-abb-tasks`
