"""สร้างชื่อไฟล์และข้อความวันที่ไทย"""
from __future__ import annotations

import datetime as dt
from typing import Optional
from urllib.parse import quote

from .config import MONTHS_TH


def parse_iso(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def thai_date(day: dt.date) -> str:
    """18 พฤศจิกายน 2569 (ปี พ.ศ. 4 หลัก)"""
    return f"{day.day} {MONTHS_TH[day.month - 1]} {day.year + 543}"


def header_text(day: dt.date, hour: Optional[int]) -> str:
    """ข้อความในกล่องข้อความหัวรายงาน เช่น 'วันที่ 18 พฤศจิกายน 2569 เวลา 13.00 น.'"""
    time_text = f"{hour:02d}.00" if hour is not None else "--.--"
    return f"วันที่ {thai_date(day)} เวลา {time_text} น."


def make_filename(hour: Optional[int], day: dt.date) -> str:
    """รายงานผลการตรวจอากาศเวลา HH.00 น. DD-MM-YY.xlsx (YY = ปี พ.ศ. 2 หลัก)"""
    hh = f"{hour:02d}" if hour is not None else "--"
    yy = (day.year + 543) % 100
    return f"รายงานผลการตรวจอากาศเวลา {hh}.00 น. {day.day:02d}-{day.month:02d}-{yy:02d}.xlsx"


def clean_filename(name: Optional[str]) -> str:
    """ชื่อไฟล์ที่ผู้ใช้แก้เอง: ตัดอักขระที่ใช้ตั้งชื่อไฟล์ไม่ได้ ใส่ .xlsx ให้ครบ คืน '' ถ้าว่าง"""
    if not name:
        return ""
    cleaned = "".join(ch for ch in name if ch not in '\\/:*?"<>|' and ord(ch) >= 32).strip().strip(".")
    if not cleaned:
        return ""
    stem = cleaned[:-5] if cleaned.lower().endswith(".xlsx") else cleaned
    return stem[:145].strip() + ".xlsx"


def content_disposition(filename: str) -> str:
    """ชื่อไฟล์ภาษาไทยต้องส่งแบบ RFC 5987 ไม่เช่นนั้นเบราว์เซอร์แสดงชื่อเพี้ยน"""
    return f"attachment; filename=\"report.xlsx\"; filename*=UTF-8''{quote(filename)}"
