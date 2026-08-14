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
- `csv_report.py` — ตรวจสอบและอ่าน CSV หลักโดยไม่เรียก NAS API
- `yard_api.py` — อ่าน Drive ShareSync API เฉพาะ NAS Yard
- `sangfor_capture.py` — login และ capture Sangfor ด้วย Chromium
- `build_backup_report.py` — สร้าง PDF ด้วย ReportLab
- `web/` — หน้าเว็บและ JavaScript
- `deploy/linux/` — installer, systemd unit, environment template และ requirements

## Data flow ที่ถูกต้อง

```text
ผู้ใช้กดสร้างรายงาน
  -> โหลด settings/credentials ที่บันทึกบน server
  -> NAS หลัก: ดาวน์โหลด abb_daily_result_YYYY-MM-DD.csv ที่ตรงกับวันรายงานเท่านั้น (authoritative)
  -> NAS หลัก: ห้ามใช้ API; อ่าน CSV ผ่าน File Station UI และใช้ส่วน AUDIT ท้าย CSV
  -> NAS Yard: อ่าน Drive ShareSync connections และ sessions
  -> Sangfor: login, sort Latest Backup, capture
  -> สร้าง PDF ตาม docs/REPORT_SPEC.md
  -> เก็บ PDF และข้อความสรุปในประวัติรายงาน
  -> ส่ง PDF ให้ browser ดาวน์โหลด
```

## กติกาที่ห้ามเปลี่ยนโดยพลการ

- CSV จาก NAS คือข้อมูลจริงของรายงาน Active Backup โดยใช้เฉพาะไฟล์
  `abb_daily_result_YYYY-MM-DD.csv` ที่ตรงกับวันรายงาน ห้ามใช้ `latest`
  หรือไฟล์วันก่อน
- ห้ามคำนวณ `Same Size`, `Audit Same Size`, `Audit Status`, `Start`, `End` ใหม่
- จัดลำดับแถวตาม Task List ที่อนุมัติและสร้างเลข `No.` ใหม่เพื่อการแสดงผลเท่านั้น
  ค่าอื่นทุกช่องต้องคงตาม CSV และ Task ที่ไม่รู้จักให้ต่อท้ายตามลำดับเดิมใน CSV
- API อนุญาตเฉพาะ NAS Yard Drive ShareSync และห้ามใช้กับ NAS หลัก
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

- รุ่นปัจจุบัน: `0.14.3-task-list-order`
- หัวหน้าอนุมัติผลลัพธ์ปัจจุบันแล้วเมื่อ 14 สิงหาคม 2569 และไม่ให้เปลี่ยนรูปแบบ
  โดยพลการ รายละเอียด baseline อยู่ใน `APPROVED_BASELINE_V0.14.3.md`
- หน้าแรกแนบภาพ Task List จาก Clipboard/ไฟล์ได้ แล้วแสดงตาราง 14 คอลัมน์
- หน้า Audit สร้างจากส่วน `AUDIT` ท้าย CSV เดียวกัน ไม่ Capture จาก Active Backup
- ตรวจค่า Last Backup จาก CSV กับ Start ใน PDF และยืนยันว่าไม่มีการสร้าง End

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
