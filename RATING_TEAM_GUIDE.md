# Prediction Rating UI — คู่มือทีมงาน (ภาษาไทย)

> **เวอร์ชัน:** 1.0 &nbsp;|&nbsp; **กลุ่มผู้ใช้:** ทีม Rating/Annotation &nbsp;|&nbsp; **URL:** `http://localhost:8000` (ผู้ดูแลระบบเป็นผู้รันเซิร์ฟเวอร์)

---

## สารบัญ

1. [แอปนี้คืออะไร](#1-แอปนี้คืออะไร)
2. [การเข้าใช้งาน](#2-การเข้าใช้งาน)
3. [ภาพรวม Workflow 5 ขั้นตอน](#3-ภาพรวม-workflow-5-ขั้นตอน)
4. [ขั้นตอนที่ 1 — โหลดภาพ Prediction](#4-ขั้นตอนที่-1--โหลดภาพ-prediction)
5. [ขั้นตอนที่ 2 — ลิงก์ผลลัพธ์ CSV (ไม่บังคับ)](#5-ขั้นตอนที่-2--ลิงก์ผลลัพธ์-csv-ไม่บังคับ)
6. [ขั้นตอนที่ 3 — ลิงก์ Scale Profile (ไม่บังคับ)](#6-ขั้นตอนที่-3--ลิงก์-scale-profile-ไม่บังคับ)
7. [ขั้นตอนที่ 4 — รีวิวภาพ](#7-ขั้นตอนที่-4--รีวิวภาพ)
8. [ขั้นตอนที่ 5 — Export ผลลัพธ์](#8-ขั้นตอนที่-5--export-ผลลัพธ์)
9. [การวาด Annotation และการแก้ไข](#9-การวาด-annotation-และการแก้ไข)
10. [คีย์ลัด (Keyboard Shortcuts)](#10-คีย์ลัด-keyboard-shortcuts)
11. [การใช้งาน Queue](#11-การใช้งาน-queue)
12. [คำถามที่พบบ่อย](#12-คำถามที่พบบ่อย)
13. [การแก้ปัญหาเบื้องต้น](#13-การแก้ปัญหาเบื้องต้น)

---

## 1. แอปนี้คืออะไร

**Prediction Rating UI** เป็นเครื่องมือภายในสำหรับตรวจและแก้ผลทำนายของโมเดลบนภาพผิวถนน โดยหน้าที่หลักของผู้ใช้งานคือ:

| การตัดสินใจ | ความหมาย |
|---|---|
| `Accept` | ภาพนี้โมเดลทำนายถูกต้อง |
| `Fix` | ภาพนี้โมเดลทำนายผิด และต้องแก้ annotation |
| `Delete` | ลบ object prediction ที่เลือก (ใน flow การแก้ไข) |

หลังรีวิวเสร็จ สามารถ export ข้อมูลเพื่อส่งต่อทีมโมเดลสำหรับทำ training/QC ต่อได้

---

## 2. การเข้าใช้งาน

1. ตรวจสอบว่าเซิร์ฟเวอร์ทำงานอยู่แล้ว
2. เปิดเบราว์เซอร์ไปที่ `http://localhost:8000`
3. เข้าสู่ระบบตามสิทธิ์ที่ได้รับ (L1/L2)

> ระบบมี autosave การตัดสินใจ/ตำแหน่งคิว/annotation อัตโนมัติ ถ้าปิดหน้าแล้วกลับมาใหม่จะต่อจากงานเดิมได้

---

## 3. ภาพรวม Workflow 5 ขั้นตอน

ลำดับงานหลักในหน้า Task Detail:

```
① Load Images → ② Link CSV (optional) → ③ Link Scale Profile (optional) → ④ Review/Fix → ⑤ Export
```

- ขั้นตอน 1 จำเป็น
- ขั้นตอน 2-3 ไม่บังคับ แต่ช่วยให้ทำงานเร็ว/แม่นยำขึ้น

---

## 4. ขั้นตอนที่ 1 — โหลดภาพ Prediction

### วิธีที่แนะนำ: Import จากเครื่องผู้ใช้

1. กด `Import Folder From PC`
2. เลือกโฟลเดอร์ภาพ prediction
3. รออัปโหลดและสแกนไฟล์

### วิธีใส่พาธโดยตรง

1. วางพาธ เช่น
   ```text
   D:\S25_DRR\predictions\20250509
   ```
2. กด `Load Path`

หลังโหลดสำเร็จ:
- Queue ด้านซ้ายจะแสดงรายการภาพ
- แถบสรุปจะแสดงจำนวน reviewed/correct/wrong/annotated
- ระบบเปิดภาพแรกที่ตรงกับ filter ปัจจุบัน

---

## 5. ขั้นตอนที่ 2 — ลิงก์ผลลัพธ์ CSV (ไม่บังคับ)

เมื่อลิงก์ `detailed_results.csv` แล้วจะเห็น bounding boxes ของโมเดลเพื่อช่วยตัดสินใจเร็วขึ้น

### วิธีลิงก์

- กด `Browse...` เพื่อเลือกไฟล์จากเครื่อง
- หรือวางพาธไฟล์ CSV แล้วกด `Load Path`

### หมายเหตุ

- ถ้าต้อง export updated CSV ควรลิงก์ CSV ก่อน
- สามารถเปิด/ปิด `Show model bounding boxes` ได้ระหว่างรีวิว
- รองรับหัวคอลัมน์รูปแบบใหม่ที่มี `Road Type`:
  `Image Filename,Road Type,Object ID,Class,Value,Unit,X1 (px),Y1 (px),X2 (px),Y2 (px),Confidence`

---

## 6. ขั้นตอนที่ 3 — ลิงก์ Scale Profile (ไม่บังคับ)

ถ้าลิงก์ `scale_profile.csv` แล้วระบบจะคำนวณค่าเชิงกายภาพจาก polygon อัตโนมัติ:

- กลุ่มพื้นที่ (alligator crack / patching / pothole / pavement): หน่วย `m^2`
- `crack`: หน่วย `m`

### วิธีลิงก์

- เลือกไฟล์ผ่าน `Browse...`
- หรือวางพาธแล้วกด `Load Path`

หากไม่ลิงก์ scale profile ยัง annotate ได้ตามปกติ แต่ค่าพื้นที่/ความยาวจะไม่ถูกคำนวณ

---

## 7. ขั้นตอนที่ 4 — รีวิวภาพ

### ปุ่มตัดสินใจหลัก

| ปุ่ม | ความหมาย |
|---|---|
| `Accept (A)` | ยืนยันว่าภาพนี้ถูกต้อง |
| `Fix (F)` | ภาพนี้ผิด ต้องแก้ annotation |
| `Delete (D)` | ลบ object prediction ที่เลือก |
| `Reset (U)` | รีเซ็ตภาพกลับเป็น `unreviewed` |
| `Undo (Z)` | ย้อนการแก้ไขล่าสุด |

### การนำทาง

- `← Prev` / `Next →`
- คีย์ `ArrowLeft` / `ArrowRight`
- เลือกภาพจาก Queue โดยตรง

### Auto-Advance

ระบบสามารถเลื่อนไปภาพถัดไปอัตโนมัติหลัง action ได้ (เปิด/ปิดได้จากปุ่ม `Auto-Advance`)

---

## 8. ขั้นตอนที่ 5 — Export ผลลัพธ์

### ตัวเลือกการส่งออก

| ปุ่ม | ผลลัพธ์ |
|---|---|
| `Export Updated CSV` | CSV ที่รวมผลแก้ไข polygon/action |
| `Export ZIP` | ชุดข้อมูลสำหรับงานฝึกโมเดล (images/annotated/labels/manifest) |
| `Export TXT` | รายชื่อไฟล์ที่ถูกคัดเลือกแบบข้อความ |

### โครงสร้าง ZIP โดยสรุป

```text
rating_export.zip
├── images/
├── annotated/
├── labels/
├── classes.txt
├── manifest.json
└── manifest.csv
```

> ก่อน Export ZIP ต้องตั้ง `Target image path` ให้ถูกต้อง เพื่อ map กับภาพต้นฉบับ

---

## 9. การวาด Annotation และการแก้ไข

### 9.1 Draw Polygon

1. เลือก class
2. กด `Draw Polygon`
3. คลิกวางจุดรอบบริเวณที่ต้องการ
4. ปิด polygon โดย double-click หรือคลิกกลับจุดแรก

### 9.2 Brush / Eraser

- `Brush`: ระบายพื้นที่แบบอิสระ ยกเมาส์แล้วระบายต่อได้
- `Eraser`: ลบรอยระบาย brush draft
- `Confirm Brush Mask`: ยืนยัน draft brush ให้กลายเป็น polygon
- `Clear Brush Draft`: ล้าง draft brush ทั้งหมด

### 9.3 การจัดการ mask/object

- เปลี่ยน class ของ mask ที่มีอยู่ได้จาก `Mask List`
- กดที่ row ใน Mask List เพื่อ select/highlight บนภาพ
- ใช้ปุ่ม keep/replace/delete ใน `Original Detections` เพื่อกำหนด action ราย object

---

## 10. คีย์ลัด (Keyboard Shortcuts)

| คีย์ | การทำงาน |
|---|---|
| `A` | Accept |
| `F` | Fix |
| `D` | Delete selected object |
| `U` | Reset เป็น unreviewed |
| `Z` | Undo |
| `ArrowLeft` / `ArrowRight` | ภาพก่อนหน้า / ถัดไป |
| `C` / `W` | alias เดิมของ Accept / Fix |
| `Ctrl/Cmd + Mouse Wheel` | Zoom ตามตำแหน่งเมาส์ |
| `Space + Drag` (หรือเมาส์กลางลาก) | Pan ภาพเมื่อ zoom แล้ว |

> คีย์ลัดจะไม่ทำงานขณะพิมพ์ใน input/textarea/select

---

## 11. การใช้งาน Queue

Queue ใช้ติดตามความคืบหน้าการรีวิวและกระโดดไปภาพที่ต้องการเร็วขึ้น

### Filter

- `All`
- `Unreviewed`
- `Wrong`
- `Completed`

ในมุมมอง `All` ระบบจะแบ่งกลุ่ม `Unreviewed` และ `Reviewed` เพื่อให้อ่านสถานะง่ายขึ้น

### Badge สถานะ

- `Unreviewed`
- `Accepted`
- `Fix`
- `N polygons`

---

## 12. คำถามที่พบบ่อย

**Q: ต้องกด save เองไหม?**  
A: ไม่ต้อง ระบบ autosave ให้อัตโนมัติหลังการเปลี่ยนแปลงหลัก

**Q: เปลี่ยนคำตัดสินย้อนหลังได้ไหม?**  
A: ได้ เลือกภาพจาก Queue แล้วกด action ใหม่ได้ทันที

**Q: ไม่มี scale profile ยังทำงานได้ไหม?**  
A: ได้ แต่ค่าเชิงกายภาพจะไม่ถูกคำนวณ

**Q: ทำไมแสดงค่า area/length แปลก?**  
A: ตรวจสอบ class ที่เลือก, scale profile ที่ลิงก์, และขอบเขต polygon ว่าปิดถูกต้อง

---

## 13. การแก้ปัญหาเบื้องต้น

### โหลดโฟลเดอร์ไม่เจอ
- ตรวจสอบพาธว่าเข้าถึงได้จากเครื่องเซิร์ฟเวอร์
- ลอง `Import Folder From PC` แทนการวางพาธ

### ไม่เห็น bounding boxes
- ตรวจว่าลิงก์ CSV สำเร็จ
- เปิด `Show model bounding boxes`
- ชื่อไฟล์ใน CSV ต้องตรงกับไฟล์ภาพจริง

### Export ZIP ไม่ได้เพราะหาไฟล์ไม่ครบ
- ตรวจ `Target image path`
- ชื่อไฟล์/นามสกุลต้องตรงกับภาพใน prediction

### งานหายหลังรีเฟรช
- ปกติระบบ autosave ให้ หากผิดปกติให้ลอง reload folder เดิม
- หากยังมีปัญหา ให้แจ้งผู้ดูแลระบบพร้อมเวลาที่เกิดเหตุ

---

*หากพบปัญหาเชิงเทคนิคเพิ่มเติม ให้ติดต่อผู้ดูแลระบบของทีมทันที*
