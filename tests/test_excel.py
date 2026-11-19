import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
import zipfile

import openpyxl
import pytest

from app import config as C
from app.config import TEMPLATE_PATH
from app.excel import TemplateError, blank_template, build_workbook, read_report

from conftest import FIXTURES


def template() -> bytes:
    return TEMPLATE_PATH.read_bytes()


def values(**by_code):
    rows = [dict.fromkeys("BCDEFGH", "") for _ in C.STATIONS]
    for code, fields in by_code.items():
        rows[[s.code for s in C.STATIONS].index(code.removeprefix("c"))].update(fields)
    return rows


def sheet_of(data: bytes):
    return openpyxl.load_workbook(io.BytesIO(data)).active


# ---------------------------------------------------------------- อ่านไฟล์

def test_template_is_valid_and_has_all_stations():
    info = read_report(template())
    assert [info.rows[s.name] for s in C.STATIONS] == list(range(4, 25))
    assert info.h == [""] * 21


def test_read_fixture_title_h_values_and_normalization():
    info = read_report((FIXTURES / "report_1300.xlsx").read_bytes())
    assert (info.round, info.date) == (13, "2026-11-18")
    assert info.title == "วันที่ 18 พฤศจิกายน 2569 เวลา 13.00 น."
    names = [s.name for s in C.STATIONS]
    assert info.h[names.index("สงขลา")] == "5.4"
    assert info.h[names.index("พัทลุง")] == "36.2"  # ในไฟล์เป็น 36.200000000000003
    assert info.h[names.index("เกษตรกาญจนดิษฐ์")] == "T"
    assert info.h[names.index("เพชรบุรี")] == "0.0"


def test_read_all_three_fixtures_rounds():
    got = {h: read_report((FIXTURES / f"report_{h:02d}00.xlsx").read_bytes()).round for h in (7, 10, 13)}
    assert got == {7: 7, 10: 10, 13: 13}


def test_not_an_xlsx_gives_thai_error():
    with pytest.raises(TemplateError, match="ไม่ใช่ไฟล์ Excel"):
        read_report(b"not a zip")


def test_other_workbook_is_rejected(tmp_path):
    wb = openpyxl.Workbook()
    wb.active["A4"] = "อื่น ๆ"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(TemplateError):
        read_report(buf.getvalue())


# ---------------------------------------------------------------- เขียนไฟล์

def test_write_values_and_types():
    out = build_workbook(
        template(),
        values(**{
            "48568": dict(B="ลมตะวันออก", C="/ กำลังอ่อน", D="เมฆเต็มท้องฟ้า", E="", F="27.1", G="5", H="5.4"),
            "48555": dict(B="ลมตะวันออกเฉียงใต้", C="/ กำลังอ่อน", D="เมฆบางส่วน", F="31.5", G="T", H="T"),
            "48465": dict(B="ลมสงบ", D="ท้องฟ้าโปร่ง", F="32", G="0", H="0.0"),
            "48474": dict(F="30.0", G="-", H="-", E="/ มีฟ้าหลัวแห้ง"),
        }),
        13, dt.date(2026, 11, 18),
    )
    ws = sheet_of(out)
    s = {s.code: s.row for s in C.STATIONS}
    r = s["48568"]
    assert [ws[f"{c}{r}"].value for c in "BCDE"] == ["ลมตะวันออก", "/ กำลังอ่อน", "เมฆเต็มท้องฟ้า", None]
    assert ws[f"F{r}"].value == 27.1 and ws[f"G{r}"].value == 5 and ws[f"H{r}"].value == 5.4  # เป็นตัวเลขจริง
    assert ws[f"G{r}"].number_format == "0.0"
    r = s["48555"]
    assert ws[f"G{r}"].value == "T" and ws[f"H{r}"].value == "T"
    r = s["48465"]
    assert ws[f"F{r}"].value == 32 and ws[f"H{r}"].value == 0
    r = s["48474"]
    assert ws[f"G{r}"].value == "-" and ws[f"E{r}"].value == "/ มีฟ้าหลัวแห้ง"


def test_untouched_rows_are_blank_and_old_values_do_not_remain():
    prev = (FIXTURES / "report_1000.xlsx").read_bytes()  # ใช้ไฟล์รอบก่อนเป็นต้นแบบ
    out = build_workbook(prev, values(**{"48568": dict(B="ลมสงบ", F="27.1", G="0", H="0")}), 13, dt.date(2026, 11, 18))
    ws = sheet_of(out)
    for s in C.STATIONS:
        if s.code != "48568":
            assert all(ws[f"{c}{s.row}"].value is None for c in "BCDEFGH"), s.name


def test_header_textbox_updated_and_other_parts_preserved():
    src = template()
    out = build_workbook(src, values(), 16, dt.date(2026, 12, 3))
    zin, zout = zipfile.ZipFile(io.BytesIO(src)), zipfile.ZipFile(io.BytesIO(out))
    assert zin.namelist() == zout.namelist()  # ครบทุกชิ้นส่วน ลำดับเดิม
    drawing = zout.read("xl/drawings/drawing1.xml").decode()
    text = "".join(re.findall(r"<a:t>([^<]*)</a:t>", drawing))
    assert text == "วันที่ 3 ธันวาคม 2569 เวลา 16.00 น."
    # รูป/สไตล์/ชีตอื่นต้องเหมือนเดิมทุกไบต์
    for name in zin.namelist():
        if name not in ("xl/worksheets/sheet1.xml", "xl/drawings/drawing1.xml"):
            assert zin.read(name) == zout.read(name), name
    # รูป (anchor) และกล่องข้อความยังอยู่
    assert "<xdr:pic>" in drawing and "<xdr:sp " in drawing
    assert 'typeface="Kanit Medium"' in drawing  # ฟอร์แมตกล่องข้อความคงเดิม


def test_every_xml_part_is_well_formed():
    out = build_workbook(template(), values(**{"48568": dict(B="ลม & <test>", F="1")}), 13, dt.date(2026, 11, 18))
    z = zipfile.ZipFile(io.BytesIO(out))
    for name in z.namelist():
        if name.endswith(".xml") or name.endswith(".rels"):
            ET.fromstring(z.read(name))  # ต้องไม่ error
    assert sheet_of(out)[f"B{C.STATION_BY_CODE['48568'].row}"].value == "ลม & <test>"


def test_data_validation_and_merged_cells_preserved():
    out = build_workbook(template(), values(), 13, dt.date(2026, 11, 18))
    ws = sheet_of(out)
    assert sorted(str(m) for m in ws.merged_cells.ranges) == ["A1:H1", "B3:C3", "D3:E3"]
    ranges = sorted(str(dv.sqref) for dv in ws.data_validations.dataValidation)
    assert ranges == ["B25", "B4:B24", "C4:C24", "D4:D24", "E4:E24", "H3"]
    z = zipfile.ZipFile(io.BytesIO(out))
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert 'mc:Ignorable="x14ac"' in sheet and "xmlns:x14ac=" in sheet  # namespace ที่ Excel ต้องใช้ไม่หาย


def test_round_07_switches_h_header_and_note():
    ws7 = sheet_of(build_workbook(template(), values(), 7, dt.date(2026, 11, 18)))
    assert ws7["H3"].value == "ฝน 24 ชม. (มม.)" and ws7["B25"].value == C.NOTE_24H
    ws13 = sheet_of(build_workbook((FIXTURES / "report_0700.xlsx").read_bytes(), values(), 13, dt.date(2026, 11, 18)))
    assert ws13["H3"].value == "ฝนสะสมวันนี้ (มม.)" and ws13["B25"].value == C.NOTE_TODAY


def test_cell_styles_are_kept():
    src = template()
    before, after = sheet_of(src), sheet_of(build_workbook(src, values(**{"48568": dict(F="27.1", G="5", H="5.4", B="ลมสงบ")}), 13, dt.date(2026, 11, 18)))
    for ref in ("B18", "F18", "G18", "H18", "E4", "A24", "H24"):
        assert before[ref].style_id == after[ref].style_id, ref
        assert before[ref].number_format == after[ref].number_format
        assert before[ref].font.name == after[ref].font.name


def test_output_can_be_used_as_next_template():
    first = build_workbook(template(), values(**{"48568": dict(F="27.1", G="5", H="5.4")}), 13, dt.date(2026, 11, 18))
    info = read_report(first)
    assert info.round == 13 and info.date == "2026-11-18"
    assert info.h[[s.code for s in C.STATIONS].index("48568")] == "5.4"
    again = build_workbook(first, values(), 16, dt.date(2026, 11, 18))
    assert read_report(again).round == 16


def test_blank_template_clears_everything():
    blank = blank_template((FIXTURES / "report_1300.xlsx").read_bytes())
    ws = sheet_of(blank)
    assert all(ws[f"{c}{r}"].value is None for r in range(4, 25) for c in "BCDEFGH")
    assert ws["A4"].value == "เพชรบุรี" and ws["H3"].value == "ฝนสะสมวันนี้ (มม.)"
