"""Golden test: ผลของระบบต้องตรงกับไฟล์ตัวอย่างรอบ 07.00 / 10.00 / 13.00 น. ทุกช่อง

ไฟล์ตัวอย่างอยู่ใน tests/fixtures เป็นข้อมูลสมมติ สร้างด้วย tests/make_fixtures.py (ไม่ใช่รายงานจริง)
เราสร้างรหัสข่าวสมมติจากค่าในไฟล์ ถอดรหัสกลับ แล้วเทียบ B–F จากนั้นเขียนไฟล์ใหม่และเทียบทุกเซลล์ B–H

หมายเหตุ: ไฟล์ตัวอย่างสร้างด้วย build_workbook เอง การเทียบไฟล์จึงเป็นการกันการเปลี่ยนแปลงโดยไม่ตั้งใจ (regression)
ไม่ได้พิสูจน์ความถูกต้องต่อ Excel ที่กรอกมือ ส่วนการถอดรหัสยังตรวจกลับด้วยรหัสข่าวจริงของสงขลา (REAL_48568)
ก่อนหน้านี้ระบบเคยเทียบกับไฟล์ Excel ที่กรอกมือจริงครบ 3 รอบ ทุกเซลล์ และผ่านแล้ว
"""
import datetime as dt
import io

import openpyxl
import pytest

from app import config as C
from app.decoder import decode_station, parse_messages
from app.excel import build_workbook, read_report

from conftest import FIXTURES
from helpers import REAL_48568, make_message

FILES = {7: "report_0700.xlsx", 10: "report_1000.xlsx", 13: "report_1300.xlsx"}
UTC = {7: "00", 10: "03", 13: "06"}


def load(hour: int):
    ws = openpyxl.load_workbook(FIXTURES / FILES[hour]).active
    rows = []
    for s in C.STATIONS:
        def cell(col):
            v = ws[f"{col}{s.row}"].value
            if v is None:
                return ""
            if isinstance(v, (int, float)):
                return f"{round(float(v), 1):.1f}"
            return str(v).strip()
        rows.append({c: cell(c) for c in "BCDEFGH"})
    return rows


@pytest.mark.parametrize("hour", [7, 10, 13])
def test_decoded_codes_reproduce_hand_filled_columns(hour):
    for s, row in zip(C.STATIONS, load(hour)):
        text = make_message(f"18{UTC[hour]}4", s.code, row["B"], row["C"], row["D"], row["E"], row["F"])
        msg = parse_messages(text).messages[0]
        got = decode_station(msg.chunks[0], msg.iw)
        assert (got.B, got.C, got.D, got.E, got.F) == (row["B"], row["C"], row["D"], row["E"], row["F"]), s.name
        assert (msg.day, msg.hour) == (18, hour)


@pytest.mark.parametrize("hour", [7, 10, 13])
def test_exported_file_equals_hand_filled_file_cell_by_cell(hour):
    expected = load(hour)
    out = build_workbook((FIXTURES / "report_1000.xlsx").read_bytes(), expected, hour, dt.date(2026, 11, 18))
    ws_out = openpyxl.load_workbook(io.BytesIO(out)).active
    ws_ref = openpyxl.load_workbook(FIXTURES / FILES[hour]).active
    for s in C.STATIONS:
        for col in "ABCDEFGH":
            a, b = ws_out[f"{col}{s.row}"].value, ws_ref[f"{col}{s.row}"].value
            if isinstance(b, float):
                assert round(a, 1) == round(b, 1), (hour, s.name, col)
            else:
                assert a == b, (hour, s.name, col, a, b)
    info = read_report(out)
    assert (info.round, info.date) == (hour, "2026-11-18")


def test_real_songkhla_code_matches_the_13_00_file_row():
    row = load(13)[[s.code for s in C.STATIONS].index("48568")]
    msg = parse_messages(REAL_48568).messages[0]
    got = decode_station(msg.chunks[0], msg.iw)
    assert (got.B, got.C, got.D, got.E, got.F) == (row["B"], row["C"], row["D"], row["E"], row["F"])
    assert (row["G"], row["H"]) == ("5.0", "5.4")  # ค่านี้มาจากช่องของ METNET ไม่ได้ถอดจากรหัส
