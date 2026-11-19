"""สร้างไฟล์ตัวอย่างรายงาน tests/fixtures/report_{0700,1000,1300}.xlsx จากข้อมูลสมมติ

ใช้เมื่อต้องการสร้างไฟล์ตัวอย่างใหม่:  .venv/Scripts/python tests/make_fixtures.py
ค่าทั้งหมดเป็นข้อมูลสมมติ (ไม่ใช่รายงานจริง) วันที่ 18-11-69 ยกเว้นแถวสงขลารอบ 13.00 น. ที่ตั้งให้ตรงกับรหัสข่าวตัวอย่าง
REAL_48568 ใน tests/helpers.py เพื่อใช้เทียบการถอดรหัส

ค่าสำคัญที่เทสต์อื่นอ้างถึง (อย่าเปลี่ยนโดยไม่แก้เทสต์):
  รอบ 10.00 พัทลุง H = 20.8   รอบ 13.00 สงขลา H = 5.4, พัทลุง H = 36.2 (เขียนเป็น 36.200000000000003 เหมือน Excel จริง),
  เกษตรกาญจนดิษฐ์ H = T, เพชรบุรี H = 0.0
"""
from __future__ import annotations

import datetime as dt
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config as C  # noqa: E402
from app.excel import build_workbook  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
NE, SE, E_ = "ลมตะวันออกเฉียงเหนือ", "ลมตะวันออกเฉียงใต้", "ลมตะวันออก"
CALM = "ลมสงบ"
W1, W2 = C.STRENGTH_WEAK, C.STRENGTH_MEDIUM
FEW, PART, MOST, MANY, FULL = "ท้องฟ้าโปร่ง", "เมฆบางส่วน", "เมฆเป็นส่วนมาก", "เมฆมาก", "เมฆเต็มท้องฟ้า"
HAZEW, FAR, RAIN, THUN = "/ มีฟ้าหลัวชื้น", "/ มีฝนตกระยะไกล", "/ มีฝนตกเป็นระยะ", "/ มีฟ้าคะนอง"

# เรียงตาม C.STATIONS (เพชรบุรี ... นราธิวาส) แต่ละแถว: ทิศ, กำลังลม, ท้องฟ้า, ลักษณะอากาศ, F, G, H
R1000 = [
    (NE, W1, FEW, "", "29.4", "0", "0.0"), (NE, W1, PART, "", "30.2", "0", "0.0"), (E_, W1, FEW, "", "29.8", "0", "0.0"),
    (SE, W1, PART, "", "31.0", "0", "0.0"), (NE, W2, MOST, "", "28.9", "0", "0.0"), (CALM, "", PART, "", "30.5", "0", "0.0"),
    (E_, W1, MOST, FAR, "29.1", "0.2", "0.2"), (NE, W1, MANY, "", "29.6", "0", "0.0"), (SE, W1, PART, "", "30.8", "T", "T"),
    (CALM, "", FULL, HAZEW, "28.7", "0", "0.0"), (NE, W1, MANY, "", "29.9", "0", "0.4"), (E_, W2, MOST, "", "29.3", "0", "0.0"),
    (SE, W1, FEW, "", "30.4", "0", "0.0"), (NE, W1, FULL, RAIN, "27.8", "1.6", "20.8"), (E_, W1, FULL, "", "28.2", "0.4", "1.2"),
    (NE, W2, FULL, RAIN, "28.0", "3.0", "9.5"), (SE, W1, FULL, "", "28.6", "0", "0.6"), (NE, W1, MANY, "", "29.2", "0", "0.0"),
    (E_, W1, FULL, HAZEW, "27.5", "0.2", "2.4"), (NE, W1, FULL, "", "28.4", "0", "0.0"), (NE, W1, FULL, RAIN, "27.9", "0.6", "1.8"),
]
R1300 = [
    (NE, W1, FEW, "", "32.1", "0", "0.0"), (NE, W1, PART, "", "33.0", "0", "0.0"), (E_, W1, FEW, "", "32.6", "0", "0.0"),
    (SE, W1, PART, "", "33.4", "0", "0.0"), (NE, W2, MOST, "", "31.5", "0", "0.0"), (CALM, "", PART, "", "33.0", "0", "0.0"),
    (E_, W1, MOST, FAR, "31.8", "1.2", "1.4"), (NE, W1, MANY, "", "32.2", "0", "0.0"), (SE, W1, PART, "", "33.3", "T", "T"),
    (CALM, "", FULL, HAZEW, "30.9", "0", "0.0"), (NE, W1, MANY, "", "32.4", "0.4", "0.8"), (E_, W2, MOST, "", "31.7", "0", "0.0"),
    (SE, W1, FEW, "", "33.1", "0", "0.0"), (NE, W1, FULL, RAIN, "28.9", "2.4", "36.2"), (E_, W1, FULL, "", "27.1", "5", "5.4"),
    (NE, W2, FULL, THUN, "29.0", "5.0", "14.5"), (SE, W1, FULL, "", "30.1", "0", "0.6"), (NE, W1, MANY, "", "31.0", "0", "0.0"),
    (E_, W1, FULL, HAZEW, "28.4", "0.8", "3.2"), (NE, W1, FULL, "", "30.6", "0", "0.0"), (NE, W1, FULL, RAIN, "28.6", "1.0", "2.8"),
]
# รอบ 07.00: H คือฝน 24 ชม.
R0700 = [
    (CALM, "", FEW, "", "25.2", "0", "0.0"), (NE, W1, FEW, "", "25.8", "0", "0.0"), (NE, W1, PART, "", "25.5", "0", "0.0"),
    (CALM, "", PART, "", "26.0", "0", "0.0"), (NE, W1, MOST, "", "25.1", "0", "0.0"), (CALM, "", FEW, "", "25.9", "0", "0.0"),
    (E_, W1, MOST, "", "25.7", "T", "3.2"), (NE, W1, MANY, "", "25.6", "0", "0.0"), (SE, W1, PART, "", "26.1", "0", "T"),
    (CALM, "", FULL, HAZEW, "25.0", "0", "0.0"), (NE, W1, MANY, "", "25.4", "0.2", "5.6"), (E_, W1, MOST, "", "25.3", "0", "0.0"),
    (CALM, "", FEW, "", "25.9", "0", "0.0"), (NE, W1, FULL, RAIN, "24.6", "4.2", "48.6"), (E_, W1, FULL, RAIN, "24.8", "1.4", "12.0"),
    (NE, W1, FULL, RAIN, "24.7", "6.0", "30.4"), (E_, W1, FULL, "", "24.9", "0", "7.8"), (NE, W1, MANY, "", "25.2", "0", "0.0"),
    (E_, W1, FULL, RAIN, "24.5", "2.0", "16.4"), (NE, W1, FULL, "", "24.8", "0", "0.4"), (NE, W1, FULL, RAIN, "24.6", "0.8", "9.2"),
]


def make(hour: int, rows: list[tuple]) -> bytes:
    values = [dict(zip("BCDEFGH", r)) for r in rows]
    assert len(values) == len(C.STATIONS)
    return build_workbook(C.TEMPLATE_PATH.read_bytes(), values, hour, dt.date(2026, 11, 18))


def add_float_noise(data: bytes, cell: str, plain: str, noisy: str) -> bytes:
    """Excel เก็บ 36.2 เป็น 36.200000000000003 ได้ ใส่ไว้เพื่อให้เทสต์การปัดค่าอ่านยังมีความหมาย"""
    zin = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            blob = zin.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                text = blob.decode("utf-8")
                pattern = re.compile(r'(<c r="%s"[^>]*>)<v>%s</v>' % (cell, re.escape(plain)))
                text, n = pattern.subn(lambda m: f"{m.group(1)}<v>{noisy}</v>", text)
                assert n == 1, cell
                blob = text.encode("utf-8")
            zout.writestr(info, blob)
    return buf.getvalue()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    row_phatthalung = C.STATION_BY_CODE["48560"].row
    (OUT / "report_0700.xlsx").write_bytes(make(7, R0700))
    (OUT / "report_1000.xlsx").write_bytes(make(10, R1000))
    f1300 = add_float_noise(make(13, R1300), f"H{row_phatthalung}", "36.2", "36.200000000000003")
    (OUT / "report_1300.xlsx").write_bytes(f1300)
    print("สร้างไฟล์ตัวอย่างใน", OUT)


if __name__ == "__main__":
    main()
