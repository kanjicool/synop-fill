from app.decoder import decode_station, parse_messages, to_knots

from helpers import REAL_48552, REAL_48568


def decode(text: str, code: str):
    parsed = parse_messages(text)
    for m in parsed.messages:
        for c in m.chunks:
            if c[0] == code:
                return decode_station(c, m.iw), m
    raise AssertionError("ไม่พบสถานี")


def d(chunk: str, iw: int = 4):
    return decode_station(chunk.split(), iw)


# ---- ตัวอย่างจริงจากหน้า METNET (ตรงกับค่าที่กรอกใน Excel) -----------------------------

def test_real_nakhon_si_thammarat_example_from_plan():
    r, m = decode(REAL_48552, "48552")
    assert (r.B, r.C, r.D, r.E, r.F) == (
        "ลมตะวันออกเฉียงเหนือ", "/ กำลังอ่อน", "เมฆเป็นส่วนมาก", "", "31.1",
    )
    assert (m.day, m.hour, m.iw) == (17, 16, 4)  # 09 UTC = 16.00 น.


def test_real_songkhla_example():
    r, m = decode(REAL_48568, "48568")
    assert (r.B, r.C, r.D, r.E, r.F) == ("ลมตะวันออก", "/ กำลังอ่อน", "เมฆเต็มท้องฟ้า", "", "27.1")
    assert (m.day, m.hour) == (18, 13)
    assert r.dew == 239 and r.f_syn == 271


# ---- ลม ------------------------------------------------------------------------------

def test_calm_when_ff_is_zero():
    r = d("48552 32460 60500 10311 20255")
    assert (r.B, r.C) == ("ลมสงบ", "")


def test_calm_when_dd_is_zero_even_if_speed_positive():
    r = d("48552 32460 60005 10311 20255")
    assert (r.B, r.C) == ("ลมสงบ", "")


def test_variable_direction_keeps_strength():
    r = d("48569 32460 89906 10248 20240")
    assert (r.B, r.C) == ("ลมแปรปรวน", "/ กำลังอ่อน")


def test_direction_slash_is_na():
    r = d("48475 32460 8//// 10296 20250")
    assert r.B == "n/a" and r.C == "" and r.D == "เมฆเต็มท้องฟ้า"


def test_direction_ranges_from_paper_table():
    cases = {"36": "ลมเหนือ", "01": "ลมเหนือ", "02": "ลมตะวันออกเฉียงเหนือ", "07": "ลมตะวันออกเฉียงเหนือ",
             "08": "ลมตะวันออก", "10": "ลมตะวันออก", "11": "ลมตะวันออกเฉียงใต้", "16": "ลมตะวันออกเฉียงใต้",
             "17": "ลมใต้", "19": "ลมใต้", "20": "ลมตะวันตกเฉียงใต้", "25": "ลมตะวันตกเฉียงใต้",
             "26": "ลมตะวันตก", "28": "ลมตะวันตก", "29": "ลมตะวันตกเฉียงเหนือ", "34": "ลมตะวันตกเฉียงเหนือ"}
    for dd, expected in cases.items():
        assert d(f"48552 32460 5{dd}05 10311 20255").B == expected, dd


def test_direction_outside_table_is_flagged_not_guessed():
    assert d("48552 32460 53805 10311 20255").B == "[dd=38]"


def test_strength_bands_in_knots():
    assert d("48552 32460 50501 10311 20255").C == "/ กำลังอ่อน"  # 01 นอต = กำลังอ่อน (ลายมือในกระดาษ)
    assert d("48552 32460 50507 10311 20255").C == "/ กำลังอ่อน"
    assert d("48552 32460 50508 10311 20255").C == "/ กำลังปานกลาง"
    assert d("48552 32460 50515 10311 20255").C == "/ กำลังปานกลาง"
    assert d("48552 32460 50516 10311 20255").C == "/ กำลังแรง"


def test_ms_converted_to_knots_with_half_up_rounding():
    assert to_knots(4, 0) == 8   # 7.776 -> 8
    assert to_knots(3, 1) == 6   # 5.832
    assert to_knots(8, 1) == 16  # 15.552
    assert to_knots(10, 4) == 10  # นอตอยู่แล้ว
    assert d("48552 32460 50504 10311 20255", iw=0).C == "/ กำลังปานกลาง"
    assert d("48552 32460 50508 10311 20255", iw=1).C == "/ กำลังแรง"


def test_half_up_not_bankers_rounding():
    # 0.5 มี 1944*x ที่ลงท้าย .5 พอดีได้ยากกับจำนวนเต็ม แต่ต้องปัดครึ่งขึ้นเสมอ ไม่ใช่ round() ของ Python
    assert (1 * 1944 + 500) // 1000 == 2  # 1.944 -> 2
    assert to_knots(1, 0) == 2


def test_ff_99_reads_real_speed_from_00fff_group():
    r = d("48552 32460 60599 00022 10311 20255")
    assert r.B == "ลมตะวันออกเฉียงเหนือ" and r.C == "/ กำลังแรง"  # 22 นอต


# ---- ท้องฟ้า -------------------------------------------------------------------------

def test_sky_table():
    expected = ["ท้องฟ้าแจ่มใส", "ท้องฟ้าโปร่ง", "ท้องฟ้าโปร่ง", "เมฆบางส่วน", "เมฆบางส่วน",
                "เมฆเป็นส่วนมาก", "เมฆเป็นส่วนมาก", "เมฆมาก", "เมฆเต็มท้องฟ้า", "มองไม่เห็นท้องฟ้า"]
    for n, text in enumerate(expected):
        assert d(f"48552 32460 {n}0504 10311 20255").D == text


def test_sky_obscured_slash_is_blank():
    assert d("48552 32460 /0504 10311 20255").D == ""


# ---- ลักษณะอากาศ (กลุ่ม 7) -----------------------------------------------------------

def test_weather_ww_10_from_plan():
    assert d("48552 32460 60504 10311 20255 71022").E == "/ มีฟ้าหลัวชื้น"


def test_weather_below_04_is_blank():
    assert d("48552 32460 60504 10311 20255 70222").E == ""


def test_weather_21_same_as_10_confirmed_by_user():
    assert d("48552 32460 60504 10311 20255 72100").E == "/ มีฟ้าหลัวชื้น"


def test_weather_unknown_ww_is_red_marker_not_guessed():
    assert d("48500 31460 50804 10298 20240 79922").E == "[ww=99]"
    assert d("48500 31460 50804 10298 20240 78000").E == "[ww=80]"  # ฝนโปรยไม่อยู่ใน dropdown


def test_weather_fog_range_40_to_49():
    assert d("48552 32460 60504 10311 20255 74500").E == "/ มีหมอก"


def test_seven_in_group_three_is_not_weather():
    # N=7 ทำให้กลุ่ม Nddff ขึ้นต้นด้วย 7 ต้องไม่ถูกเข้าใจเป็นกลุ่มลักษณะอากาศ
    r = d("48552 32460 70504 10311 20255")
    assert r.D == "เมฆมาก" and r.E == ""


def test_only_first_seven_group_is_used():
    assert d("48552 32460 60504 10311 20255 71000 76000").E == "/ มีฟ้าหลัวชื้น"


def test_seven_after_333_is_not_weather():
    # หลัง 333 กลุ่ม 7 คือฝน 24 ชม. ไม่ใช่ลักษณะอากาศ
    assert d("48568 01460 81003 10271 20239 333 70270").E == ""
    assert d("48552 32460 50504 10311 20255 333 76000").E == ""


# ---- อุณหภูมิ ------------------------------------------------------------------------

def test_temperature_positive_and_negative():
    assert d("48552 32460 60504 10311 20255").F == "31.1"
    r = d("48552 32460 60504 11121 20255")
    assert r.F == "-12.1" and r.f_syn == -121


def test_temperature_missing_is_blank():
    assert d("48552 32460 60504 1//// 20255").F == ""


# ---- NIL / ข้อความไม่ครบ / หลายสถานี -------------------------------------------------

def test_nil_station():
    parsed = parse_messages("AAXX 18064\n48520 NIL=")
    assert decode_station(parsed.messages[0].chunks[0], 4).nil


def test_incomplete_message_is_treated_as_no_data():
    assert d("48520 32460").nil


def test_multiple_stations_separated_by_equals():
    p = parse_messages("AAXX 18064\n48465 32460 00000 10305 20240=\n48474 31460 30905 10312 20250 70402=")
    assert len(p.messages) == 1
    assert [c[0] for c in p.messages[0].chunks] == ["48465", "48474"]
    assert decode_station(p.messages[0].chunks[1], 4).E == "/ มีหมอกควัน"


def test_multiple_aaxx_blocks_with_different_times():
    p = parse_messages(REAL_48552 + "\n\n" + REAL_48568)
    assert [(m.day, m.hour) for m in p.messages] == [(17, 16), (18, 13)]


# ---- หัวข้อความ ----------------------------------------------------------------------

def test_header_converts_utc_to_thai_time():
    m = parse_messages("AAXX 18064\n48568 32460 60504").messages[0]
    assert (m.day, m.hour, m.utc, m.iw) == (18, 13, 6, 4)


def test_header_crossing_midnight_moves_to_next_day():
    m = parse_messages("AAXX 17184\n48568 32460 60504").messages[0]  # 18 UTC = 01.00 น. วันถัดไป
    assert (m.day, m.hour, m.day_utc) == (18, 1, 17)


def test_missing_aaxx_is_a_problem():
    p = parse_messages("48568 01460 81003")
    assert p.problems and not p.messages


def test_bad_header_is_a_problem():
    assert parse_messages("AAXX 18").problems


def test_empty_text_is_not_a_problem():
    p = parse_messages("   ")
    assert not p.problems and not p.messages


def test_header_15_utc_is_22_00_thai_same_day():
    m = parse_messages("AAXX 18154\n48568 32460 60504").messages[0]
    assert (m.day, m.hour, m.utc) == (18, 22, 15)
