from app.rain import expected_h, fmt_tenths, parse_rain, parse_temp, rrr_text


def p(v):
    return parse_rain(v)


def test_parse_values():
    assert p("").kind == "empty" and p("  ").kind == "empty" and p(None).kind == "empty"
    assert p("-").kind == "dash"
    assert p("T").kind == "T" and p("t").kind == "T"
    assert p("0.5") == p("0.5") and p("0.5").tenths == 5
    assert p("27").tenths == 270
    assert p("100.0").tenths == 1000


def test_parse_rejects_typos():
    for bad in ("7,5", "abc", "1.25", "-3", "1e3", "٣", "5 5", "12345"):
        assert p(bad).kind == "bad", bad


def test_fmt_tenths():
    assert fmt_tenths(0) == "0.0" and fmt_tenths(17) == "1.7" and fmt_tenths(-121) == "-12.1"


def test_expected_h_examples_from_plan():
    # H เดิม = 1.2, G = 0.5 -> 1.7
    e = expected_h(p("1.2"), p("0.5"))
    assert (e.tenths, e.is_trace) == (17, False)
    # H เดิม = T, G = 0.0 -> T
    e = expected_h(p("T"), p("0.0"))
    assert (e.tenths, e.is_trace) == (0, True)
    # T + T -> T, 0 + T -> T
    assert expected_h(p("0"), p("T")).is_trace
    assert expected_h(p("T"), p("T")).is_trace
    # T + 0.3 -> 0.3 (T ถือเป็น 0 แต่ผลรวมไม่ใช่ 0)
    e = expected_h(p("T"), p("0.3"))
    assert (e.tenths, e.is_trace) == (3, False)


def test_no_float_error_on_accumulation():
    # 0.1 + 0.2 ต้องได้ 0.3 พอดี (float ให้ 0.30000000000000004)
    e = expected_h(p("0.1"), p("0.2"))
    assert fmt_tenths(e.tenths) == "0.3"


def test_expected_h_unknown_when_missing_values():
    assert expected_h(p("-"), p("1")) is None
    assert expected_h(p("1"), p("")) is None
    assert expected_h(p("abc"), p("1")) is None


def test_parse_temp():
    assert parse_temp("27.1").tenths == 271
    assert parse_temp("-12.1").tenths == -121
    assert parse_temp("30").tenths == 300
    assert parse_temp("").kind == "empty"
    assert parse_temp("27,1").kind == "bad"


def test_rrr_text_table_from_plan():
    assert rrr_text("005") == "5 มม."
    assert rrr_text("000") == "0 มม."
    assert rrr_text("989") == "989 มม. ขึ้นไป"
    assert "T" in rrr_text("990")
    assert rrr_text("995") == "0.5 มม."
    assert rrr_text("999") == "0.9 มม."
    assert "ไม่ได้วัด" in rrr_text("///")
