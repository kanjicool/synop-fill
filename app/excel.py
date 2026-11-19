"""อ่าน/เขียนไฟล์รายงาน .xlsx โดยแก้ XML ตรง ๆ (ไม่ใช้ openpyxl เขียน)

เหตุผล: ไฟล์จริงมี "กล่องข้อความวันที่/เวลา" ที่หัวรายงาน รูปใต้ตาราง และ dropdown
openpyxl ทิ้งกล่องข้อความตอนบันทึก การแก้เฉพาะเซลล์ที่จำเป็นทำให้ทุกอย่างอื่นคงเดิม
"""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.sax.saxutils import escape

from . import config as C
from .filename import header_text

SHEET = "xl/worksheets/sheet1.xml"
SHARED = "xl/sharedStrings.xml"
DRAWING = "xl/drawings/drawing1.xml"
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
COLUMNS = ("B", "C", "D", "E", "F", "G", "H")
NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")


class TemplateError(ValueError):
    """ไฟล์ต้นแบบใช้ไม่ได้ ข้อความเป็นภาษาไทยพร้อมแสดงให้ผู้ใช้"""


@dataclass
class ReportInfo:
    rows: dict[str, int] = field(default_factory=dict)  # ชื่อสถานี -> แถวจริงในไฟล์
    h: list[str] = field(default_factory=list)  # ค่าคอลัมน์ H เรียงตาม STATIONS ("" ถ้าว่าง)
    round: Optional[int] = None
    date: Optional[str] = None  # ISO
    title: Optional[str] = None


# ------------------------------------------------------------------ อ่านไฟล์

def _open(data: bytes) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TemplateError("ไฟล์นี้ไม่ใช่ไฟล์ Excel (.xlsx) หรือไฟล์เสีย") from exc
    names = set(z.namelist())
    if SHEET not in names or SHARED not in names:
        raise TemplateError("ไฟล์นี้ไม่ใช่ไฟล์รายงานผลการตรวจอากาศ (ไม่พบ Sheet1)")
    return z


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(z.read(SHARED))
    out = []
    for si in root.findall(f"{{{NS_MAIN}}}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t")))
    return out


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{NS_MAIN}}}t"))
    v = cell.find(f"{{{NS_MAIN}}}v")
    if v is None or v.text is None:
        return ""
    if kind == "s":
        return shared[int(v.text)]
    return v.text


def _normalize_number(text: str) -> str:
    """ตัดเศษ float ที่เพี้ยนใน Excel เช่น 32.299999999999997 -> 32.3"""
    try:
        d = Decimal(text).quantize(Decimal("0.1"))
    except InvalidOperation:
        return text
    return str(d)


def _read_title(z: zipfile.ZipFile) -> tuple[Optional[str], Optional[int], Optional[str]]:
    if DRAWING not in z.namelist():
        return None, None, None
    xml = z.read(DRAWING).decode("utf-8")
    text = "".join(re.findall(r"<a:t>([^<]*)</a:t>", xml))
    m = re.search(r"วันที่\s*(\d+)\s*(\S+)\s*(\d{4})\s*เวลา\s*(\d+)\s*\.\s*(\d+)", text)
    if not m:
        return (text or None), None, None
    try:
        month = C.MONTHS_TH.index(m.group(2)) + 1
        date = dt.date(int(m.group(3)) - 543, month, int(m.group(1))).isoformat()
    except (ValueError, IndexError):
        date = None
    hour = int(m.group(4))
    return text, (hour if hour in C.ROUNDS else None), date


def read_report(data: bytes) -> ReportInfo:
    """อ่านชื่อสถานี/แถว ค่า H เดิม และวัน-รอบจากหัวรายงาน ใช้ตรวจว่าไฟล์เป็นต้นแบบที่ถูกต้อง"""
    z = _open(data)
    shared = _shared_strings(z)
    sheet = ET.fromstring(z.read(SHEET))
    cells: dict[str, ET.Element] = {c.get("r"): c for c in sheet.iter(f"{{{NS_MAIN}}}c")}
    rows: dict[str, int] = {}
    for r in range(C.FIRST_ROW, C.LAST_ROW + 1):
        cell = cells.get(f"A{r}")
        if cell is not None:
            rows[_cell_text(cell, shared).strip()] = r
    missing = [s.name for s in C.STATIONS if s.name not in rows]
    if missing:
        raise TemplateError(
            "ไฟล์นี้ไม่ใช่ไฟล์ต้นแบบของรายงานนี้ ไม่พบสถานี: " + ", ".join(missing[:5])
            + (" ..." if len(missing) > 5 else "")
        )
    h: list[str] = []
    for s in C.STATIONS:
        cell = cells.get(f"H{rows[s.name]}")
        text = _cell_text(cell, shared).strip() if cell is not None else ""
        h.append(_normalize_number(text) if NUMERIC.match(text) else text)
    title, hour, date = _read_title(z)
    return ReportInfo(rows=rows, h=h, round=hour, date=date, title=title)


# ------------------------------------------------------------------ เขียนไฟล์

def _cell_pattern(ref: str) -> re.Pattern[str]:
    return re.compile(rf'<c r="{ref}"[^>]*?/>|<c r="{ref}"[^>]*?>.*?</c>', re.DOTALL)


def _style_attr(cell_xml: str) -> str:
    m = re.search(r'\ss="(\d+)"', cell_xml.split(">", 1)[0])
    return f' s="{m.group(1)}"' if m else ""


def _cell_xml(ref: str, style: str, col: str, value: str) -> str:
    if value == "":
        return f'<c r="{ref}"{style}/>'
    if col in ("F", "G", "H") and NUMERIC.match(value):
        d = Decimal(value)
        text = "0" if d == 0 else format(d.normalize(), "f")
        return f'<c r="{ref}"{style}><v>{text}</v></c>'
    return f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'


def _set_cell(sheet: str, ref: str, col: str, value: str) -> str:
    pattern = _cell_pattern(ref)
    m = pattern.search(sheet)
    if not m:
        raise TemplateError(f"ไฟล์ต้นแบบไม่มีเซลล์ {ref} (โครงสร้างไฟล์ไม่ตรงกับที่ระบบรู้จัก)")
    new = _cell_xml(ref, _style_attr(m.group(0)), col, value)
    return sheet[: m.start()] + new + sheet[m.end():]


_RUNS = re.compile(r"(<xdr:txBody>.*?<a:p>(?:<a:pPr[^>]*/>)?)((?:<a:r>.*?</a:r>)+)(<a:endParaRPr)", re.DOTALL)
_RPR = re.compile(r"<a:rPr[^>]*/>|<a:rPr.*?</a:rPr>", re.DOTALL)


def _set_title(drawing: str, text: str) -> str:
    """รวมข้อความกล่องข้อความเป็น run เดียว ใช้ฟอร์แมตของ run แรก (ทุก run ใช้ฟอนต์/สีเดียวกัน)"""
    m = _RUNS.search(drawing)
    if not m:
        return drawing
    first_rpr = _RPR.search(m.group(2))
    rpr = first_rpr.group(0) if first_rpr else ""
    run = f"<a:r>{rpr}<a:t>{escape(text)}</a:t></a:r>"
    return drawing[: m.start(2)] + run + drawing[m.end(2):]


def _write_zip(src: zipfile.ZipFile, replaced: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = replaced.get(info.filename, src.read(info.filename))
            new_info = zipfile.ZipInfo(info.filename, info.date_time)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            dst.writestr(new_info, data)
    return out.getvalue()


def build_workbook(
    template: bytes,
    values: list[dict[str, str]],
    hour: Optional[int],
    day: dt.date,
) -> bytes:
    """เขียนค่าทุกสถานีลงไฟล์ต้นแบบ

    values: รายการตาม C.STATIONS แต่ละรายการมีคีย์ B..H (สตริง, "" = เว้นว่าง)
    ทุกแถวถูกเขียนทับ (รวมสถานีที่ข้าม จะว่าง) เพื่อไม่ให้ค่าเก่าจากไฟล์รอบก่อนค้างอยู่
    """
    z = _open(template)
    info = read_report(template)
    sheet = z.read(SHEET).decode("utf-8")
    for station, row_values in zip(C.STATIONS, values):
        row = info.rows[station.name]
        for col in COLUMNS:
            sheet = _set_cell(sheet, f"{col}{row}", col, row_values.get(col, ""))
    is24 = hour == 7
    sheet = _set_cell(sheet, "H3", "H3", C.H_LABEL_24H if is24 else C.H_LABEL_TODAY)
    sheet = _set_cell(sheet, "B25", "B25", C.NOTE_24H if is24 else C.NOTE_TODAY)
    replaced = {SHEET: sheet.encode("utf-8")}
    if DRAWING in z.namelist():
        drawing = z.read(DRAWING).decode("utf-8")
        replaced[DRAWING] = _set_title(drawing, header_text(day, hour)).encode("utf-8")
    return _write_zip(z, replaced)


def blank_template(source: bytes) -> bytes:
    """สร้างไฟล์ต้นแบบเปล่าจากไฟล์รายงานที่กรอกแล้ว (ล้างค่า B–H ทุกสถานี หัวรายงานเป็น ...)"""
    z = _open(source)
    info = read_report(source)
    sheet = z.read(SHEET).decode("utf-8")
    for station in C.STATIONS:
        for col in COLUMNS:
            sheet = _set_cell(sheet, f"{col}{info.rows[station.name]}", col, "")
    sheet = _set_cell(sheet, "H3", "H3", C.H_LABEL_TODAY)
    sheet = _set_cell(sheet, "B25", "B25", C.NOTE_TODAY)
    replaced = {SHEET: sheet.encode("utf-8")}
    if DRAWING in z.namelist():
        drawing = z.read(DRAWING).decode("utf-8")
        replaced[DRAWING] = _set_title(drawing, "วันที่ ... เวลา ... น.").encode("utf-8")
    return _write_zip(z, replaced)
