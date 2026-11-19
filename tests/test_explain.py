from app.decoder import explain

from helpers import REAL_48568


def by_token(items):
    return {i["token"]: i for i in items}


def test_real_songkhla_every_group_is_explained():
    items = explain(REAL_48568, "48568")
    tokens = [i["token"] for i in items]
    assert tokens == [
        "AAXX 18064", "48568", "01460", "81003", "10271", "20239", "30119", "40127",
        "57016", "60051", "70262", "8387/", "333", "58019", "60056", "70270",
    ]
    t = by_token(items)
    assert t["48568"]["lines"] == ["= สงขลา"]
    assert "13.00 น." in " ".join(t["AAXX 18064"]["lines"])


def test_which_groups_go_into_the_sheet():
    t = by_token(explain(REAL_48568, "48568"))
    assert t["81003"]["cls"] == "use" and "B" in t["81003"]["badge"] and "D" in t["81003"]["badge"]
    assert t["10271"]["cls"] == "use" and t["10271"]["badge"] == "ลงช่อง F"
    assert t["20239"]["cls"] == "chk"
    assert t["30119"]["cls"] == "skip" and t["60051"]["cls"] == "skip"
    # ww=02 (< 04) ช่อง E ว่าง
    assert t["70262"]["badge"] == "ช่อง E ว่าง"


def test_wind_group_explains_each_number():
    lines = by_token(explain(REAL_48568, "48568"))["81003"]["lines"]
    assert any("เมฆเต็มท้องฟ้า" in l and "ช่อง D" in l for l in lines)
    assert any("100°" in l and "ลมตะวันออก" in l for l in lines)
    assert any("3 นอต" in l and "กำลังอ่อน" in l for l in lines)


def test_values_in_pressure_and_rain_groups():
    t = by_token(explain(REAL_48568, "48568"))
    assert "1011.9" in t["30119"]["lines"][0]
    assert "1012.7" in t["40127"]["lines"][0]
    assert "5 มม." in " ".join(t["60051"]["lines"]) and "6 ชม." in " ".join(t["60051"]["lines"])


def test_seven_after_333_is_explained_as_24h_rain_not_weather():
    t = by_token(explain(REAL_48568, "48568"))
    item = t["70270"]
    assert "ฝน 24 ชม." in item["title"] and "27.0" in item["lines"][0] and item["cls"] == "skip"


def test_ms_header_shows_conversion():
    text = "AAXX 18060\n48500 31460 50504 10298 20240 71000"
    lines = by_token(explain(text, "48500"))["50504"]["lines"]
    assert any("1.944" in l and "8 นอต" in l for l in lines)  # 4 m/s -> 7.776 -> 8


def test_ww_not_in_table_says_red_cell():
    t = by_token(explain("AAXX 18064\n48500 31460 50804 10298 20240 79922", "48500"))
    assert any("ช่องแดง" in l for l in t["79922"]["lines"])


def test_second_seven_group_is_marked_unused():
    items = explain("AAXX 18064\n48500 31460 50804 10298 20240 71000 76000", "48500")
    t = by_token(items)
    assert t["71000"]["cls"] == "use" and t["76000"]["cls"] == "skip"


def test_ff_99_reads_00fff_group():
    t = by_token(explain("AAXX 18064\n48552 32460 60599 00022 10311 20255", "48552"))
    assert "22" in t["00022"]["lines"][0] and t["00022"]["cls"] == "use"


def test_nil_station():
    items = explain("AAXX 18064\n48520 NIL=", "48520")
    assert [i["token"] for i in items] == ["AAXX 18064", "48520", "NIL"]


def test_unreadable_text_returns_none():
    assert explain("", "48568") is None
    assert explain("48568 01460 81003", "48568") is None


def test_other_station_in_text_is_explained_with_its_own_name():
    items = explain("AAXX 18064\n48465 32460 00000 10305 20240", "48568")  # วางผิดสถานี
    assert by_token(items)["48465"]["lines"] == ["= เพชรบุรี"]
