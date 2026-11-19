import io
import json
from urllib.parse import quote

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import config as C
from app.filename import clean_filename
from app.main import app

from conftest import FIXTURES
from helpers import REAL_48552, REAL_48568

client = TestClient(app)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IDX = {s.code: i for i, s in enumerate(C.STATIONS)}


def blank_rows():
    return [{"code": s.code} for s in C.STATIONS]


def payload(rows=None, **kw):
    data = {"rows": rows or blank_rows(), "ref": {"y": 2026, "m": 11, "d": 18}}
    data.update(kw)
    return data


def done_row(code, **kw):
    base = {"code": code, "status": "done", "has_code": True, "msg_time": {"day": 18, "hour": 13}}
    base.update(kw)
    return base


def rows_with(**by_code):
    rows = blank_rows()
    for code, row in by_code.items():
        rows[IDX[code.removeprefix("c")]] = row
    return rows


# ---------------------------------------------------------------- พื้นฐาน

def test_health_identifies_the_app():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "app": "synop-fill"}


def test_config_lists_stations_options_and_reference():
    j = client.get("/api/config").json()
    assert len(j["stations"]) == 21 and j["stations"][0] == {"code": "48465", "name": "เพชรบุรี", "row": 4}
    assert j["stations"][-1]["name"] == "นราธิวาส" and j["stations"][-1]["row"] == 24
    assert "n/a" in j["options"]["B"] and len(j["options"]["E"]) == 12
    assert {"dir", "spd", "sky", "ww"} <= set(j["reference"])
    assert [r["h"] for r in j["rounds"]] == [7, 10, 13, 16]


def test_index_page_is_served_without_cache():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- /api/decode

def test_decode_real_songkhla():
    j = client.post("/api/decode", json={"code": "48568", "raw": REAL_48568}).json()
    assert (j["B"], j["C"], j["D"], j["E"], j["F"]) == ("ลมตะวันออก", "/ กำลังอ่อน", "เมฆเต็มท้องฟ้า", "", "27.1")
    assert j["msg_time"] == {"day": 18, "hour": 13} and j["has_code"] and not j["problem"]
    assert j["f_syn"] == 271 and j["dew"] == 239
    assert j["explain"][0]["token"] == "AAXX 18064"


def test_decode_empty_is_quiet():
    j = client.post("/api/decode", json={"code": "48568", "raw": "  "}).json()
    assert j["problem"] == "" and not j["has_code"] and j["explain"] is None


def test_decode_wrong_station_names_the_other_station():
    j = client.post("/api/decode", json={"code": "48568", "raw": REAL_48552}).json()
    assert "นครศรีธรรมราช" in j["problem"] and "48552" in j["problem"] and not j["has_code"]
    assert j["explain"]  # ยังอธิบายรหัสให้ดูได้


def test_decode_without_aaxx_and_nil():
    assert "AAXX" in client.post("/api/decode", json={"code": "48568", "raw": "48568 01460 81003"}).json()["problem"]
    j = client.post("/api/decode", json={"code": "48520", "raw": "AAXX 18064\n48520 NIL="}).json()
    assert j["nil"] and not j["has_code"] and j["msg_time"] == {"day": 18, "hour": 13}


def test_decode_picks_own_station_from_a_bulletin():
    raw = "AAXX 18064\n48465 32460 00000 10305 20240=\n48568 01460 81003 10271 20239 70262=\n48474 31460 30905 10312 20250="
    j = client.post("/api/decode", json={"code": "48568", "raw": raw}).json()
    assert j["F"] == "27.1" and j["B"] == "ลมตะวันออก"


# ---------------------------------------------------------------- /api/check

def test_check_returns_summary():
    rows = rows_with(**{"48568": done_row("48568", F="27.1", G="5", H="5.4", f_syn=271)})
    j = client.post("/api/check", json=payload(rows)).json()
    assert j["round"] == 13 and j["filled"] == 1 and j["counts"]["err"] == 0
    assert j["filename"] == "รายงานผลการตรวจอากาศเวลา 13.00 น. 18-11-69.xlsx"
    assert len(j["flags"]) == 21


def test_check_rejects_wrong_station_list():
    bad = payload([{"code": "48465"}])
    assert client.post("/api/check", json=bad).status_code == 422


def test_check_rejects_junk():
    r = client.post("/api/check", json={"rows": "x"})
    assert r.status_code == 422 and "ไม่ถูกต้อง" in r.json()["detail"]


# ---------------------------------------------------------------- /api/prev-file

def test_prev_file_reads_h_round_and_date():
    data = (FIXTURES / "report_1000.xlsx").read_bytes()
    r = client.post("/api/prev-file", files={"file": ("a.xlsx", data, XLSX)})
    j = r.json()
    assert r.status_code == 200 and j["round"] == 10 and j["date"] == "2026-11-18"
    assert len(j["h"]) == 21 and j["h"][IDX["48560"]] == "20.8"


def test_prev_file_rejects_wrong_type_size_and_content():
    r = client.post("/api/prev-file", files={"file": ("a.csv", b"x", "text/csv")})
    assert r.status_code == 422 and ".xlsx" in r.json()["detail"]
    r = client.post("/api/prev-file", files={"file": ("a.xlsx", b"not a zip", XLSX)})
    assert r.status_code == 422 and "ไม่ใช่ไฟล์ Excel" in r.json()["detail"]
    r = client.post("/api/prev-file", files={"file": ("big.xlsx", b"0" * (C.MAX_UPLOAD_BYTES + 10), XLSX)})
    assert r.status_code == 422 and "5 MB" in r.json()["detail"]


# ---------------------------------------------------------------- /api/export

def export(data, **extra):
    form = {"payload": json.dumps(data)}
    form.update(extra.pop("form", {}))
    return client.post("/api/export", data=form, **extra)


def good_rows():
    return rows_with(**{
        "48568": done_row("48568", B="ลมตะวันออก", C="/ กำลังอ่อน", D="เมฆเต็มท้องฟ้า", F="27.1", G="5", H="5.4", f_syn=271),
        "48555": done_row("48555", B="ลมสงบ", D="เมฆบางส่วน", F="31.5", G="T", H="T", f_syn=315),
    })


def test_export_creates_valid_workbook_with_thai_filename():
    r = export(payload(good_rows()))
    assert r.status_code == 200 and r.headers["content-type"] == XLSX
    name = "รายงานผลการตรวจอากาศเวลา 13.00 น. 18-11-69.xlsx"
    assert f"filename*=UTF-8''{quote(name)}" in r.headers["content-disposition"]
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    row = C.STATION_BY_CODE["48568"].row
    assert [ws[f"{c}{row}"].value for c in "ABCDFGH"] == [
        "สงขลา", "ลมตะวันออก", "/ กำลังอ่อน", "เมฆเต็มท้องฟ้า", 27.1, 5, 5.4,
    ]
    assert ws[f"G{C.STATION_BY_CODE['48555'].row}"].value == "T"


def test_export_uses_user_filename():
    r = export(payload(good_rows()), form={"filename": 'รายงาน/ทดสอบ:1?'})
    assert f"filename*=UTF-8''{quote('รายงานทดสอบ1.xlsx')}" in r.headers["content-disposition"]


def test_export_is_blocked_while_red_cells_remain():
    rows = good_rows()
    rows[IDX["48465"]] = done_row("48465", E="[ww=99]")
    r = export(payload(rows))
    assert r.status_code == 422 and "ต้องแก้ 1 ช่อง" in r.json()["detail"]


def test_export_is_blocked_when_round_unknown():
    r = export(payload(rows_with(**{"48568": {"code": "48568", "status": "done", "F": "27.1"}})))
    assert r.status_code == 422 and "รอบ" in r.json()["detail"]


def test_export_with_round_override_when_no_time_in_codes():
    rows = rows_with(**{"48568": {"code": "48568", "status": "done", "F": "27.1", "G": "0", "H": "0"}})
    r = export(payload(rows, round_override=10, date_override="2026-11-18"))
    assert r.status_code == 200
    assert "10.00" in r.headers["content-disposition"] or quote("10.00") in r.headers["content-disposition"]


def test_export_with_previous_file_as_template_overwrites_all_rows():
    prev = (FIXTURES / "report_1000.xlsx").read_bytes()
    r = export(payload(good_rows()), files={"template": ("prev.xlsx", prev, XLSX)})
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    # สถานีที่ไม่ได้กรอกต้องว่าง ไม่ใช่ค่าเก่าจากไฟล์ 10.00
    assert ws["F4"].value is None and ws["H17"].value is None
    assert ws[f"F{C.STATION_BY_CODE['48568'].row}"].value == 27.1


def test_export_rejects_bad_template_and_bad_payload():
    r = export(payload(good_rows()), files={"template": ("x.xlsx", b"junk", XLSX)})
    assert r.status_code == 422 and "ไม่ใช่ไฟล์ Excel" in r.json()["detail"]
    r = client.post("/api/export", data={"payload": "not json"})
    assert r.status_code == 422
    r = client.post("/api/export", data={"payload": json.dumps({"rows": []})})
    assert r.status_code == 422


def test_export_does_not_leave_files_behind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    export(payload(good_rows()))
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- ชื่อไฟล์

@pytest.mark.parametrize("raw,expected", [
    ("", ""), (None, ""), ("   ", ""), ("..", ""), ("a.xlsx", "a.xlsx"), ("A.XLSX", "A.xlsx"),
    ("report", "report.xlsx"), ('a/b\\c:d*e?f"g<h>i|j', "abcdefghij.xlsx"),
])
def test_clean_filename(raw, expected):
    assert clean_filename(raw) == expected


def test_clean_filename_keeps_extension_when_truncating():
    out = clean_filename("ก" * 300)
    assert out.endswith(".xlsx") and len(out) <= 150
