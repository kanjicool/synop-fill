"""สร้าง templates/template.xlsx (ไฟล์ต้นแบบเปล่า) จากไฟล์รายงานที่กรอกแล้ว

วิธีใช้:  .venv/Scripts/python script/make_template.py "docs/ref/รายงานผลการตรวจอากาศเวลา 10.00 น. 18-11-69.xlsx"
ล้างค่า B–H ทุกสถานีและตั้งหัวรายงานเป็น "วันที่ ... เวลา ... น." โดยคงฟอนต์ เส้น dropdown กล่องข้อความและรูปไว้
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import TEMPLATE_PATH  # noqa: E402
from app.excel import blank_template  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1])
    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_bytes(blank_template(source.read_bytes()))
    print(f"สร้างไฟล์ต้นแบบแล้ว: {TEMPLATE_PATH} ({TEMPLATE_PATH.stat().st_size} ไบต์)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
