# เอกสารส่งมอบโครงการให้ผู้พัฒนาคนถัดไป

## ภาพรวม

Pylon Backup Report เป็นเว็บแอป Python ภายในองค์กรสำหรับสร้างรายงาน PDF รายวัน
จากสามแหล่งข้อมูล:

1. Synology Active Backup ของ NAS หลัก
2. Synology Drive ShareSync ของ NAS Yard
3. ภาพหลักฐานหน้า VM Backup จาก Sangfor aCloud

ระบบ production ทำงานบน AlmaLinux 8 ซึ่งเป็น Zabbix server แต่ตัวโปรแกรมแยก
เป็น systemd service ชื่อ `backup-report` และใช้พอร์ต 8780

## จุดเริ่มอ่านโค้ด

- `app.py` — HTTP server, login/session, settings, report history และ orchestration
- `synology_api.py` — DSM login, API discovery และ authenticated requests
- `api_collector.py` — ดาวน์โหลด/อ่าน CSV หลักและ normalize ข้อมูลจาก NAS APIs
- `sangfor_capture.py` — login และ capture Sangfor ด้วย Chromium
- `build_backup_report.py` — สร้าง PDF ด้วย ReportLab
- `web/` — หน้าเว็บและ JavaScript
- `deploy/linux/` — installer, systemd unit, environment template และ requirements

## Data flow ที่ถูกต้อง

```text
ผู้ใช้กดสร้างรายงาน
  -> โหลด settings/credentials ที่บันทึกบน server
  -> NAS หลัก: ดาวน์โหลด abb_daily_result_latest.csv (authoritative)
  -> NAS หลัก: อ่าน Active Backup API เพื่อข้อมูลประกอบ/ตรวจเทียบ
  -> NAS Yard: อ่าน Drive ShareSync connections และ sessions
  -> Sangfor: login, sort Latest Backup, capture
  -> สร้าง PDF ตาม docs/REPORT_SPEC.md
  -> เก็บ PDF และข้อความสรุปในประวัติรายงาน
  -> ส่ง PDF ให้ browser ดาวน์โหลด
```

## กติกาที่ห้ามเปลี่ยนโดยพลการ

- CSV จาก NAS คือข้อมูลจริงของรายงาน Active Backup
- ห้ามคำนวณ `Same Size`, `Audit Same Size`, `Audit Status`, `Start`, `End` ใหม่
- API ใช้เสริมและแจ้งความต่างเท่านั้น ห้ามเขียนทับ CSV
- ห้ามเพิ่มหน้า PDF หรือเปลี่ยนลำดับหน้าโดยไม่มีการยืนยันจากเจ้าของระบบ
- รายงานเก่าหกไฟล์เป็นแม่แบบที่หัวหน้าอนุมัติ แต่ไม่เก็บใน Git เพราะมีข้อมูลบริษัท
- หากต้องแก้ layout ให้ขอไฟล์แม่แบบจากเจ้าของระบบแล้ว render เทียบทุกหน้า

## Production paths

| รายการ | Path/ค่า |
|---|---|
| Application | `/opt/backup-report/app` |
| Environment | `/etc/backup-report/backup-report.env` |
| Runtime data | `/var/lib/backup-report` |
| Reports | `/var/lib/backup-report/reports` |
| Captures | `/var/lib/backup-report/captures` |
| Service | `backup-report` |
| Port | `8780` |

ตรวจสถานะด้วย:

```bash
systemctl status backup-report --no-pager -l
curl -sS http://127.0.0.1:8780/health
journalctl -u backup-report -n 100 --no-pager -o cat
```

## สถานะ ณ วันที่ส่งมอบ

- รุ่นปัจจุบัน: `0.9.0-legacy-report-pattern`
- โครงรายงานถูกปรับตาม PDF เก่าหกฉบับแล้ว
- QA ล่าสุดใช้ 17 รายการ, 2 รายการ Check, 10 โฟลเดอร์ Yard
- ตรวจพบและเทียบค่า Start/End จาก CSV ใน PDF ครบทั้ง 34 ค่า
- การ QA ในเครื่องพัฒนาไม่มี credentials จริงของ Sangfor จึงใช้ภาพหน้า login
  เป็น placeholder; production ใช้ credentials ที่บันทึกบน server

## ขั้นตอนรับงานด้วย Claude Code

1. Clone repository และสร้าง branch ใหม่ก่อนแก้
2. เปิด Claude Code ที่ root ของ repository เพื่อให้โหลด `CLAUDE.md`
3. ใช้ prompt ใน `docs/CLAUDE_START_PROMPT_TH.md` สำหรับอ่านระบบก่อน โดยยัง
   ไม่ให้แก้โค้ด
4. ให้ Claude เสนอแผนและรายการไฟล์ที่จะเปลี่ยน
5. หลังอนุมัติจึงให้แก้ ทดสอบ และส่งผล validation
6. Review diff และ PDF ที่ render แล้วก่อน merge/deploy

ห้ามใส่ credential จริงใน prompt, issue, commit หรือไฟล์ตัวอย่าง หากต้องทดสอบ
production ให้เจ้าของระบบอนุญาตเป็นครั้ง ๆ และใช้ค่าที่เก็บอยู่บน server เท่านั้น
