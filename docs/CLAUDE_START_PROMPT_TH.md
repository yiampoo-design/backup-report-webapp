# Prompt เริ่มงานสำหรับ Claude Code

เปิด Claude Code ที่ root ของ repository แล้วส่งข้อความนี้เป็นงานแรก:

```text
โปรดอ่าน CLAUDE.md, README.md, docs/HANDOFF_TH.md,
docs/REPORT_SPEC.md, docs/ARCHITECTURE.md, docs/DEPLOYMENT.md,
docs/OPERATIONS.md และ docs/SECURITY.md ให้ครบก่อน

จากนั้นตรวจโครงสร้าง repository และ git log โดยยังไม่แก้ไฟล์ ไม่ติดตั้ง
dependency ไม่เชื่อมต่อ NAS/Sangfor/Zabbix production และไม่แสดงหรือค้นหา
credential ใด ๆ

สรุปให้ฉันเป็นภาษาไทย:
1. สถาปัตยกรรมและ data flow ของระบบ
2. แหล่งข้อมูล authoritative และ field ใดที่ห้ามคำนวณหรือเขียนทับ
3. ลำดับหน้า PDF และเงื่อนไขการสร้างหน้า Check
4. ขั้นตอน build, test, release และ deploy ของรุ่นปัจจุบัน
5. ไฟล์สำคัญที่เกี่ยวข้องกับแต่ละส่วน
6. ความเสี่ยง ข้อมูลที่ยังขาด หรือคำถามที่ต้องถามเจ้าของระบบก่อนแก้

จบด้วยแผนตรวจรับ repository แบบ read-only และรอให้ฉันอนุมัติก่อนลงมือ
ห้ามคิด business rule หรือรูปแบบรายงานขึ้นใหม่เอง หากเอกสารไม่ชัดให้ถาม
```

## Prompt เมื่อต้องการให้แก้งานรายการหนึ่ง

แทน `<รายละเอียดงาน>` ด้วยสิ่งที่ต้องการ แล้วส่งหลังจากตรวจรับรอบแรก:

```text
งานที่ต้องการ: <รายละเอียดงาน>

ก่อนแก้ โปรดอ่าน CLAUDE.md และ docs/REPORT_SPEC.md อีกครั้ง ตรวจโค้ดและ test
ที่เกี่ยวข้อง แล้วเสนอ:
- ความเข้าใจ requirement โดยไม่เติม business rule เอง
- รายการไฟล์ที่จะเปลี่ยน
- ผลกระทบต่อ authoritative CSV, ลำดับหน้า PDF และ production
- วิธีทดสอบ รวมถึงวิธี render/ตรวจทุกหน้า เทียบ Last Backup กับ Start และยืนยันว่าไม่มี End

ให้สร้าง branch ใหม่ก่อนแก้ ห้ามใช้ credential จริงหรือเชื่อม production จนกว่า
ฉันจะอนุญาตโดยชัดเจน หาก requirement คลุมเครือให้ถามก่อน ห้ามเดา
หลังแก้ให้รายงาน diff โดยสรุป คำสั่งทดสอบ ผลทดสอบ และข้อจำกัดทั้งหมด
```

## ข้อมูลที่เจ้าของระบบอาจต้องส่งเพิ่มเป็นครั้ง ๆ

- PDF เก่าที่ใช้เทียบหน้าตา ส่งผ่านช่องทางภายใน ไม่ commit เข้า Git
- CSV ตัวอย่างที่ลบ/ปิดบังข้อมูลอ่อนไหวแล้ว
- Screenshot ตัวอย่างที่ปิดบัง URL, username และข้อมูลบริษัทตามความเหมาะสม
- Expected result ที่เจ้าของระบบยืนยันเป็นลายลักษณ์อักษร

ไม่ควรส่ง password, token, session cookie หรือไฟล์ environment ผ่าน prompt
หรือ GitHub
