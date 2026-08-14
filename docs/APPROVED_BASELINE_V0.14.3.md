# Approved production baseline: v0.14.3

สถานะ: หัวหน้าอนุมัติผลลัพธ์ปัจจุบันแล้วเมื่อวันที่ 14 สิงหาคม 2569
(Asia/Bangkok) และแจ้งว่าไม่ต้องแก้รูปแบบเพิ่มเติม เอกสารนี้เป็นจุดอ้างอิงสำหรับ
ผู้ดูแลและผู้พัฒนาคนถัดไป ห้ามเปลี่ยนกติกาหรือรูปแบบโดยคาดเดาเอง

## แหล่งข้อมูลที่อนุญาต

| ส่วนรายงาน | แหล่งข้อมูล | ข้อห้าม |
|---|---|---|
| NAS หลัก / Active Backup | ไฟล์ `abb_daily_result_YYYY-MM-DD.csv` ที่วันที่ตรงกับวันรายงาน ดาวน์โหลดผ่านหน้า File Station หรืออัปโหลดด้วยมือเป็น fallback | ห้ามเรียก Synology API, ห้ามใช้ `latest`, ห้ามแทนด้วยไฟล์วันก่อน |
| ภาพ Task List | ภาพที่ผู้ใช้วางจาก Clipboard หรือเลือกไฟล์ | เป็นภาพประกอบเท่านั้น ห้าม OCR หรือใช้แก้ค่า CSV |
| รายละเอียด Audit | ส่วน `AUDIT` ที่ต่อท้าย CSV ฉบับเดียวกัน | ห้ามดึงค่าจาก Active Backup API หรือเดาแทนข้อมูลที่ขาด |
| Yard / Drive ShareSync | Web API เฉพาะ NAS Yard | ห้ามนำค่าจาก Yard มาแทนข้อมูล NAS หลัก |
| Sangfor aCloud | Headless Chromium capture | ต้องยืนยันว่า Latest Backup เรียงใหม่ไปเก่า |

## กติกาตาราง Active Backup

- แสดง 14 คอลัมน์ตาม `docs/REPORT_SPEC.md`
- `Last Backup` จาก CSV แสดงในคอลัมน์ `Start`
- ไม่มีคอลัมน์ `End` และห้ามสร้างค่าขึ้นเอง
- `Same Size`, `Audit Same Size`, `Audit Status` และค่าอื่นทุกช่องต้องตรง CSV
- เปลี่ยนได้เฉพาะตำแหน่งแถวและเลข `No.` เพื่อให้ตรงกับ Task List ที่อนุมัติ
- Task ที่ไม่อยู่ในรายการมาตรฐานให้ต่อท้ายตามลำดับเดิมใน CSV

ลำดับ Task มาตรฐาน:

1. `STOCK_Backup_APP_SQLBak_0000`
2. `EXPRESS_Backup_Full_0000`
3. `ERP-WEB_Backup_APCHE_PHP_WebApp_0000`
4. `ERP-DB_Backup_SQLBak_0000`
5. `MOBILE_Backup_WebApp_0000`
6. `TIGERSOFT_Backup_Payroll_0000`
7. `TIGERSOFT2023_Backup_APP_0000`
8. `TIGERSOFT2023_Backup_DB_0000`
9. `ERP-APP-Demo_Backup_WebApp_0015`
10. `ERP-DB-Demo_Backup_SQLBak_0015`
11. `ERP-TEST_Backup_WebApp-SQLBak_0030`
12. `ALFRESCO-DB_Backup_AlfDB_0100`
13. `ALFRESCO-WEB_Backup_Content_0130`
14. `MA-APP_Backup_Web_SQLBak_0200`

## ลำดับหน้า PDF

1. ภาพ Task List (ถ้ามี) และตาราง Active Backup
2. หน้ารายละเอียดจาก CSV `AUDIT` หนึ่งหน้าต่อรายการ `Check` หรือสถานะไม่สำเร็จ
3. Yard / Drive ShareSync
4. Sangfor HCI เป็นหน้าสุดท้าย

ห้ามเพิ่มหน้า `Data Integrity and Audit Details` ที่เคยถูกถอดออกเพราะข้อมูลซ้ำ

## การตรวจสอบก่อนออก release

1. รัน unit tests ทั้งหมดและตรวจ syntax ของ Python/JavaScript
2. ตรวจว่าไม่มี credential, CSV จริง, PDF บริษัท, capture, log หรือ runtime data ใน Git
3. สร้าง PDF ตัวอย่างและ render ตรวจทุกหน้า
4. เทียบ `Last Backup` ใน CSV กับ `Start` ใน PDF และยืนยันว่าไม่มี `End`
5. ตรวจจำนวนหน้า Audit ให้ตรงจำนวนรายการที่เข้าเงื่อนไข
6. หาก schema/ชื่อไฟล์/ส่วน `AUDIT` เปลี่ยน ให้หยุดสร้างรายงาน แจ้ง observed กับ expected และรอผู้มีอำนาจอนุมัติ ห้ามเดา mapping ใหม่

## Production

- Service: `backup-report`
- Port: `8780`
- Code: `/opt/backup-report/app`
- Environment: `/etc/backup-report/backup-report.env`
- Mutable data: `/var/lib/backup-report`

ข้อมูลลับและข้อมูลบริษัททั้งหมดต้องอยู่เฉพาะบน production server และถูกกันออกจาก
Git ด้วย `.gitignore`
