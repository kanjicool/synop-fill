from app import config as C
from app.report import build_report
from app.schemas import CheckIn, PrevIn, RefDate, RowIn

IDX = {s.code: i for i, s in enumerate(C.STATIONS)}


def make(rows_by_code=None, ref=(2026, 11, 18), **kwargs) -> CheckIn:
    rows = [RowIn(code=s.code) for s in C.STATIONS]
    for code, fields in (rows_by_code or {}).items():
        rows[IDX[code]] = RowIn(code=code, **fields)
    y, m, d = ref
    return CheckIn(rows=rows, ref=RefDate(y=y, m=m, d=d), **kwargs)


def done(day=18, hour=13, **extra):
    base = dict(status="done", has_code=True, msg_time={"day": day, "hour": hour})
    base.update(extra)
    return base


def flag(report, code, col):
    return report["flags"][IDX[code]].get(col)


# ---------------------------------------------------------------- วัน / รอบ / ชื่อไฟล์

def test_round_and_date_come_from_latest_message():
    rep = build_report(make({"48568": done(), "48552": done(day=17, hour=16)}))
    assert rep["round"] == 13 and rep["day"] == 18 and rep["date"] == "2026-11-18"
    assert rep["latest"] == {"day": 18, "hour": 13, "from": "สงขลา", "count": 1}
    assert rep["filename"] == "รายงานผลการตรวจอากาศเวลา 13.00 น. 18-11-69.xlsx"
    assert rep["title_text"] == "วันที่ 18 พฤศจิกายน 2569 เวลา 13.00 น."


def test_station_being_filled_already_sets_the_round():
    # ยังไม่กดถัดไป (status pending) แต่รหัสข่าวถอดได้แล้ว ต้องรู้รอบทันที เพื่อแสดงค่า H รอบก่อน
    rep = build_report(make({"48568": dict(status="pending", has_code=True, msg_time={"day": 18, "hour": 13})}))
    assert rep["round"] == 13 and rep["latest"]["from"] == "สงขลา"
    skipped = build_report(make({"48568": dict(status="skipped", msg_time={"day": 18, "hour": 13})}))
    assert skipped["round"] is None
    wrong = build_report(make({"48568": dict(status="pending", problem="รหัสผิดสถานี", msg_time={"day": 18, "hour": 13})}))
    assert wrong["round"] is None


def test_older_message_is_flagged_as_different_time():
    rep = build_report(make({"48568": done(), "48552": done(day=17, hour=16)}))
    f = flag(rep, "48552", "S")
    assert f["lvl"] == "warn" and "17" in f["msg"] and "16.00" in f["msg"]
    assert flag(rep, "48568", "S") is None


def test_no_messages_means_unknown_round():
    rep = build_report(make({"48568": dict(status="done", F="27.1")}))
    assert rep["round"] is None and rep["filename"].startswith("รายงานผลการตรวจอากาศเวลา --.00 น.")
    assert any("ยังไม่ทราบรอบ" in i["text"] for i in rep["issues"])


def test_round_and_date_override():
    rep = build_report(make({"48568": done()}, date_override="2026-11-17", round_override=10))
    assert (rep["date"], rep["round"], rep["day"]) == ("2026-11-17", 10, 17)
    assert "10.00" in rep["filename"] and "17-11-69" in rep["filename"]


def test_invalid_override_is_ignored():
    rep = build_report(make({"48568": done()}, date_override="not-a-date", round_override=99))
    assert rep["date"] == "2026-11-18" and rep["round"] == 13


def test_message_day_after_reference_is_previous_month():
    # วันนี้ 2 ธ.ค. แต่ข้อความเป็นวันที่ 30 -> 30 พ.ย.
    rep = build_report(make({"48568": done(day=30)}, ref=(2026, 12, 2)))
    assert rep["date"] == "2026-11-30"


def test_year_wrap_in_january():
    rep = build_report(make({"48568": done(day=31)}, ref=(2027, 1, 1)))
    assert rep["date"] == "2026-12-31"


def test_day_32_means_first_of_next_month():
    rep = build_report(make({"48568": done(day=32, hour=1)}, ref=(2026, 11, 30)))
    assert rep["date"] == "2026-12-01"


def test_latest_handles_month_wrap():
    rep = build_report(make({"48568": done(day=1, hour=7), "48552": done(day=31, hour=16)}, ref=(2026, 12, 1)))
    assert rep["latest"]["day"] == 1 and rep["latest"]["from"] == "สงขลา"


# ---------------------------------------------------------------- ตัวตรวจค่า

def test_temperature_range_dewpoint_and_code_mismatch():
    rep = build_report(make({
        "48465": done(F="45.0"),
        "48474": done(F="25.0", dew=270, f_syn=250),
        "48475": done(F="20.0", f_syn=271),
        "48500": done(F="27,1"),
    }))
    assert "นอกช่วง" in flag(rep, "48465", "F")["msg"]
    assert "จุดน้ำค้าง" in flag(rep, "48474", "F")["msg"]
    assert "ต่างจากอุณหภูมิในรหัสข่าว" in flag(rep, "48475", "F")["msg"]
    assert flag(rep, "48500", "F")["lvl"] == "err"


def test_red_cells_from_decoder_markers():
    rep = build_report(make({
        "48475": done(B="n/a"), "48500": done(E="[ww=99]"), "48517": done(B="[dd=38]"),
    }))
    # n/a (เครื่องวัดลมเสีย) เป็นค่าที่ถูกต้องตามกระดาษ จึงเตือนแต่ไม่บล็อก
    assert flag(rep, "48475", "B")["lvl"] == "warn"
    assert flag(rep, "48500", "E")["lvl"] == "err" and "99" in flag(rep, "48500", "E")["msg"]
    assert flag(rep, "48517", "B")["lvl"] == "err"
    assert rep["counts"]["err"] == 2


def test_wrong_station_code_text_is_error():
    rep = build_report(make({"48568": dict(status="done", problem="รหัสข่าวนี้เป็นของ เพชรบุรี (48465) ไม่ใช่สถานีนี้")}))
    assert flag(rep, "48568", "S")["lvl"] == "err"


def test_rain_values_validation():
    rep = build_report(make({
        "48465": done(G="7,5", H=""),
        "48474": done(G="-", H="-"),
        "48475": done(G="", H=""),
        "48500": done(G="150", H="150"),
    }))
    assert flag(rep, "48465", "G")["lvl"] == "err"
    assert flag(rep, "48474", "G")["lvl"] == "note"
    assert flag(rep, "48475", "G")["lvl"] == "note" and "ยังไม่กรอก" in flag(rep, "48475", "G")["msg"]
    assert flag(rep, "48500", "G")["lvl"] == "warn"  # เกิน 100 มม.


def test_skipped_row_has_no_empty_rain_notes():
    rep = build_report(make({"48465": dict(status="skipped")}))
    assert rep["flags"][IDX["48465"]] == {}


def test_missing_stations_listed():
    rep = build_report(make({"48568": done()}))
    assert rep["filled"] == 1 and len(rep["missing"]) == 20 and "สงขลา" not in rep["missing"]


# ---------------------------------------------------------------- ฝนสะสมเทียบรอบก่อน

PREV_1000 = ["0"] * 21
PREV_1000[IDX["48560"]] = "20.8"
PREV_1000[IDX["48568"]] = "0.4"
PREV_1000[IDX["48555"]] = "0"


def check_prev(rows, round_prev=10, hour=13, date="2026-11-18", **kw):
    prev = PrevIn(h=PREV_1000, round=round_prev, date=date)
    return build_report(make({c: done(hour=hour, **f) for c, f in rows.items()}, prev=prev, **kw))


def test_phatthalung_real_case_is_warned():
    rep = check_prev({"48560": dict(G="7.5", H="36.2")})
    f = flag(rep, "48560", "H")
    assert f["lvl"] == "warn" and "20.8" in f["msg"] and "28.3" in f["msg"] and "36.2" in f["msg"]


def test_consistent_accumulation_has_no_flag():
    rep = check_prev({"48568": dict(G="5", H="5.4"), "48555": dict(G="T", H="T")})
    assert flag(rep, "48568", "H") is None and flag(rep, "48555", "H") is None


def test_accumulation_less_than_previous_is_error():
    rep = check_prev({"48560": dict(G="0", H="10.0")})
    assert flag(rep, "48560", "H")["lvl"] == "err"


def test_previous_file_must_be_the_round_before():
    rep = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=13)  # รอบ 13 ใช้ไฟล์ 13 ไม่ได้
    assert rep["prev_list"] is None and rep["prev_note"] and flag(rep, "48560", "H") is None


def test_previous_file_from_another_day_is_not_used():
    rep = check_prev({"48560": dict(G="7.5", H="36.2")}, date="2026-11-17")
    assert rep["prev_list"] is None and rep["prev_note"]


def test_round_16_uses_13_file_and_round_10_does_not_check():
    rep16 = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=13, hour=16)
    assert rep16["round"] == 16 and rep16["prev_list"] is not None
    rep10 = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=7, hour=10)
    assert rep10["prev_list"] is None and rep10["prev_note"] is None


def test_round_07_has_24h_labels_and_no_accumulation_check():
    rep = check_prev({"48560": dict(G="7.5", H="36.2")}, hour=7)
    assert rep["round"] == 7 and rep["h_label"] == "ฝน 24 ชม. (มม.)" and rep["prev_list"] is None
    assert "ฝน 24 ชม. หมายถึง" in rep["footnote"]
    other = build_report(make({"48568": done()}))
    assert other["h_label"] == "ฝนสะสมวันนี้ (มม.)" and other["footnote"].startswith("ฝนสะสมวันนี้ หมายถึง")


# ---------------------------------------------------------------- schema

def test_rows_must_be_all_stations_in_order():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CheckIn(rows=[RowIn(code="48465")], ref=RefDate(y=2026, m=11, d=18))


def test_round_22_is_supported_and_uses_the_16_file():
    rep = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=16, hour=22)
    assert rep["round"] == 22 and rep["prev_list"] is not None
    assert rep["filename"] == "รายงานผลการตรวจอากาศเวลา 22.00 น. 18-11-69.xlsx"
    assert rep["title_text"] == "วันที่ 18 พฤศจิกายน 2569 เวลา 22.00 น."
    wrong = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=22, hour=22)
    assert wrong["prev_list"] is None and wrong["prev_note"]
    skip = check_prev({"48560": dict(G="7.5", H="36.2")}, round_prev=13, hour=22)  # ข้ามรอบได้ ขอแค่เป็นรอบก่อนหน้า
    assert skip["prev_list"] is not None


def test_any_hour_is_accepted_as_round():
    assert check_prev({"48568": {}}, round_prev=7, hour=1)["round"] == 1
    assert check_prev({"48568": {}}, round_prev=7, hour=19)["round"] == 19
