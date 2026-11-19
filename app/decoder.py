"""แยกและถอดรหัสข้อความ SYNOP ของสถานีเดียว (คอลัมน์ B–F) และอธิบายรหัสทีละกลุ่ม

กฎสำคัญ (ดู docs/decoding-rules.md หัวข้อ 5.0):
- นับรหัสสถานีเป็นกลุ่มที่ 1 กลุ่มที่ 3 คือ Nddff (ท้องฟ้า ทิศลม กำลังลม)
- ลักษณะอากาศ: กลุ่มแรกที่ขึ้นต้นด้วย 7 นับจากกลุ่มที่ 4 เฉพาะ Section 1 (ก่อน 222/333/444/555)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import config as C
from .rain import rrr_text, tr_label

SECTION_MARKERS = ("222", "333", "444", "555")
_FIVE = re.compile(r"^[0-9/]{5}$")


def _fm(pattern: str, string: str):
    """re.fullmatch ที่ให้ตัวเลขหมายถึง 0-9 เท่านั้น (ไม่รับเลขไทย/อาหรับที่ Python มองเป็นตัวเลข)"""
    return re.fullmatch(pattern, string, re.ASCII)


@dataclass
class Message:
    day: int  # วันที่ตามเวลาไทย
    hour: int  # ชั่วโมงตามเวลาไทย
    iw: int
    hdr: str  # YYGGi เช่น "18064"
    day_utc: int
    utc: int
    chunks: list[list[str]] = field(default_factory=list)


@dataclass
class ParseResult:
    messages: list[Message] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass
class Decoded:
    nil: bool = False
    B: str = ""
    C: str = ""
    D: str = ""
    E: str = ""
    F: str = ""
    f_syn: Optional[int] = None  # อุณหภูมิในรหัส หน่วย 0.1 °C
    dew: Optional[int] = None  # จุดน้ำค้างในรหัส หน่วย 0.1 °C


def direction_text(n: int) -> Optional[str]:
    if n == 0:
        return "ลมสงบ"
    if n == 99:
        return "ลมแปรปรวน"
    if n in (35, 36, 1):
        return "ลมเหนือ"
    if 2 <= n <= 7:
        return "ลมตะวันออกเฉียงเหนือ"
    if 8 <= n <= 10:
        return "ลมตะวันออก"
    if 11 <= n <= 16:
        return "ลมตะวันออกเฉียงใต้"
    if 17 <= n <= 19:
        return "ลมใต้"
    if 20 <= n <= 25:
        return "ลมตะวันตกเฉียงใต้"
    if 26 <= n <= 28:
        return "ลมตะวันตก"
    if 29 <= n <= 34:
        return "ลมตะวันตกเฉียงเหนือ"
    return None


def strength_text(knots: Optional[int]) -> str:
    if knots is None or knots <= 0:
        return ""
    if knots <= 7:
        return C.STRENGTH_WEAK
    if knots <= 15:
        return C.STRENGTH_MEDIUM
    return C.STRENGTH_STRONG


def to_knots(speed: int, iw: int) -> int:
    """iw = 0/1 คือ m/s ต้องคูณ 1.944 แล้วปัดครึ่งขึ้นเป็นจำนวนเต็ม (ใช้จำนวนเต็มล้วน)"""
    if iw in (0, 1):
        return (speed * C.KNOT_FACTOR_MILLI + 500) // 1000
    return speed


def parse_messages(text: str) -> ParseResult:
    out = ParseResult()
    t = text.replace("\r", " ").strip()
    if not t:
        return out
    parts = re.split(r"AAXX", t, flags=re.IGNORECASE)[1:]
    if not parts:
        out.problems.append(
            "ไม่พบบรรทัด AAXX ในข้อความ ต้องคัดลอกบรรทัดที่ขึ้นต้นด้วย AAXX มาด้วย เพื่อให้รู้วันและเวลา"
        )
        return out
    for seg in parts:
        toks = seg.split()
        header = toks.pop(0) if toks else ""
        if not _fm(r"\d{5}", header):
            out.problems.append(f"หัวข้อความ AAXX ไม่ถูกต้อง: {header or '(ว่าง)'}")
            continue
        day, utc, iw = int(header[0:2]), int(header[2:4]), int(header[4])
        local = utc + C.THAI_UTC_OFFSET
        day_local = day
        if local >= 24:
            local -= 24
            day_local = day + 1
        chunks = [c.split() for c in " ".join(toks).split("=")]
        chunks = [c for c in chunks if c]
        out.messages.append(Message(day_local, local, iw, header, day, utc, chunks))
    return out


def _section1(tokens: list[str]) -> list[str]:
    for i, tok in enumerate(tokens):
        if i > 2 and tok in SECTION_MARKERS:
            return tokens[:i]
    return tokens


def _speed(tokens_sec1: list[str], ffs: str) -> Optional[int]:
    if _fm(r"\d\d", ffs) and ffs != "99":
        return int(ffs)
    if ffs == "99" and len(tokens_sec1) > 3 and _fm(r"00\d{3}", tokens_sec1[3]):
        return int(tokens_sec1[3][2:])
    return None


def decode_station(tokens: list[str], iw: int) -> Decoded:
    if len(tokens) < 2 or tokens[1] == "NIL" or len(tokens) < 3:
        return Decoded(nil=True)
    g3 = tokens[2]
    if not _FIVE.match(g3):
        return Decoded(nil=True)
    sec1 = _section1(tokens)
    n_char, dd, ffs = g3[0], g3[1:3], g3[3:5]
    ff = _speed(sec1, ffs)
    knots = to_knots(ff, iw) if ff is not None else None

    b = c = ""
    if dd == "//":
        b = "n/a"
    elif _fm(r"\d\d", dd):
        n = int(dd)
        if n == 0 or ff == 0:
            b = "ลมสงบ"
        else:
            b = direction_text(n) or f"[dd={dd}]"
            c = strength_text(knots)

    d = C.SKY[int(n_char)] if n_char in "0123456789" else ""

    e = ""
    for k in range(3, len(sec1)):  # กลุ่มที่ 4 เป็นต้นไป
        tok = sec1[k]
        if _fm(r"7[0-9/]{4}", tok):
            ws = tok[1:3]
            if _fm(r"\d\d", ws):
                w = int(ws)
                if w >= C.WW_MIN:
                    e = C.WW.get(w, f"[ww={ws}]")
            break  # ใช้กลุ่ม 7 กลุ่มแรกเท่านั้น

    f_text, f_syn, dew = "", None, None
    for k in range(3, len(sec1)):
        tok = sec1[k]
        if _fm(r"1[01]\d{3}", tok):
            f_syn = (-1 if tok[1] == "1" else 1) * int(tok[2:])
            f_text = f"{f_syn / 10:.1f}"
            break
    for k in range(3, len(sec1)):
        tok = sec1[k]
        if _fm(r"2[01]\d{3}", tok):
            dew = (-1 if tok[1] == "1" else 1) * int(tok[2:])
            break
    return Decoded(False, b, c, d, e, f_text, f_syn, dew)


def find_station_chunk(parsed: ParseResult, code: str) -> Optional[tuple[Message, list[str]]]:
    for m in parsed.messages:
        for c in m.chunks:
            if c and c[0] == code:
                return m, c
    return None


def first_station_chunk(parsed: ParseResult) -> Optional[tuple[Message, list[str]]]:
    for m in parsed.messages:
        for c in m.chunks:
            if c and _fm(r"\d{5}", c[0]):
                return m, c
    return None


# ---------------------------------------------------------------- คำอธิบายรหัส

_IR = {
    "0": "มีกลุ่มฝนทั้ง Section 1 และ 3",
    "1": "มีกลุ่มฝนใน Section 1",
    "2": "มีกลุ่มฝนใน Section 3 (หลัง 333)",
    "3": "ไม่มีกลุ่มฝน เพราะไม่มีฝนตก",
    "4": "ไม่มีกลุ่มฝน เพราะไม่ได้วัดฝน",
}
_IX = {
    "1": "มีกลุ่ม 7 (คนตรวจ)",
    "2": "ไม่มีกลุ่ม 7 เพราะไม่มีลักษณะอากาศที่ต้องรายงาน (คนตรวจ)",
    "3": "ไม่มีกลุ่ม 7 เพราะไม่มีข้อมูล (คนตรวจ)",
    "4": "มีกลุ่ม 7 (เครื่องอัตโนมัติ)",
    "5": "ไม่มีกลุ่ม 7 เพราะไม่มีลักษณะอากาศที่ต้องรายงาน (เครื่องอัตโนมัติ)",
    "6": "ไม่มีกลุ่ม 7 เพราะไม่มีข้อมูล (เครื่องอัตโนมัติ)",
    "7": "มีกลุ่ม 7 (เครื่องอัตโนมัติ)",
}


def _pressure(v4: str) -> str:
    n = int(v4)
    value = n / 10 if n >= 5000 else 1000 + n / 10
    return f"{value:.1f} hPa"


def _tendency(a: int) -> str:
    if a <= 3:
        return "ความกดอากาศสูงขึ้น"
    if a == 4:
        return "ความกดอากาศคงที่"
    return "ความกดอากาศต่ำลง"


def _signed(tok: str) -> str:
    return ("−" if tok[1] == "1" else "") + f"{int(tok[2:]) / 10:.1f}"


def explain(text: str, code: str) -> Optional[list[dict]]:
    """อธิบายรหัสข่าวทีละกลุ่ม คืน None ถ้าอ่านไม่ได้

    แต่ละรายการ: token, title, lines[], badge, cls (use = ลงช่อง, chk = ใช้ตรวจ, skip = ไม่ลงตาราง)
    """
    parsed = parse_messages(text)
    if not parsed.messages:
        return None
    hit = find_station_chunk(parsed, code) or first_station_chunk(parsed)
    if hit is None:
        return None
    m, c = hit
    items: list[dict] = []

    def add(token: str, title: str, lines: list[str], badge: str, cls: str) -> None:
        items.append({"token": token, "title": title, "lines": lines, "badge": badge, "cls": cls})

    unit_hdr = (
        "เมตร/วินาที (ระบบคูณ 1.944 ให้เป็นนอตก่อนเทียบเกณฑ์กำลังลม)"
        if m.iw <= 1
        else "นอต (ใช้ค่าตรง ๆ ได้เลย)"
    )
    add(
        f"AAXX {m.hdr}",
        "หัวข้อความ (วัน เวลา และหน่วยของความเร็วลม)",
        [
            "AAXX = รหัสข่าวตรวจอากาศผิวพื้น (SYNOP)",
            f"{m.hdr[0:2]} = วันที่ {m.day_utc} (นับตามเวลา UTC)",
            f"{m.hdr[2:4]} = {m.hdr[2:4]}.00 UTC บวก 7 ชม. = {m.hour:02d}.00 น. เวลาไทย"
            + (f" ของวันที่ {m.day}" if m.day != m.day_utc else ""),
            f"{m.hdr[4]} = ความเร็วลมเป็น{unit_hdr}",
        ],
        "ใช้ตั้งวัน เวลา และชื่อไฟล์",
        "use",
    )

    station = C.STATION_BY_CODE.get(c[0])
    add(
        c[0],
        "รหัสสถานี",
        [f"= {station.name}" if station else "ไม่อยู่ในรายการ 21 สถานีของรายงานนี้"],
        "ใช้หาแถวในไฟล์",
        "use" if station else "skip",
    )
    if len(c) > 1 and c[1] == "NIL":
        add("NIL", "ไม่มีข้อมูล", ["สถานีนี้ส่งข่าวมาแต่ไม่มีข้อมูล"], "แถวนี้ว่าง (สีเทา)", "skip")
        return items

    sec1 = _section1(c)
    rest = c[len(sec1):]

    g2 = sec1[1] if len(sec1) > 1 else ""
    if _FIVE.match(g2):
        add(
            g2,
            "ตัวบอกว่ามีกลุ่มฝนและกลุ่ม 7 หรือไม่ (iR iX h VV)",
            [
                f"iR={g2[0]} → {_IR.get(g2[0], 'ไม่ทราบความหมาย')}",
                f"iX={g2[1]} → {_IX.get(g2[1], 'ไม่ทราบความหมาย')}",
                "h = ความสูงฐานเมฆต่ำสุด · VV = ทัศนวิสัย",
            ],
            "ไม่ลงตาราง",
            "skip",
        )

    ffs = ""
    g3 = sec1[2] if len(sec1) > 2 else ""
    if _FIVE.match(g3):
        n_char, dd, ffs = g3[0], g3[1:3], g3[3:5]
        ff = _speed(sec1, ffs)
        knots = to_knots(ff, m.iw) if ff is not None else None
        lines: list[str] = []
        if n_char == "9":
            lines.append(f"N=9 → มองไม่เห็นท้องฟ้า เพราะหมอกหรือปรากฏการณ์อื่นบัง → {C.SKY[9]} (ช่อง D)")
        elif n_char in "0123456789":
            lines.append(f"N={n_char} → เมฆปกคลุมท้องฟ้า {n_char} ส่วนจาก 8 → {C.SKY[int(n_char)]} (ช่อง D)")
        else:
            lines.append(f"N={n_char} → ไม่มีค่าเมฆ (ช่อง D ว่าง)")
        if dd == "//":
            lines.append("dd=// → ไม่มีค่าทิศลม → n/a (ช่อง B เป็นช่องแดง)")
        elif _fm(r"\d\d", dd):
            n = int(dd)
            if n == 0 or ff == 0:
                lines.append(f"{'dd=00' if n == 0 else 'ff=00'} → ลมสงบ (ช่อง B = ลมสงบ ช่อง C ว่าง)")
            elif n == 99:
                lines.append("dd=99 → ทิศแปรปรวน → ลมแปรปรวน (ช่อง B)")
            else:
                lines.append(
                    f"dd={dd} → ทิศ {n * 10}° (เลข dd คูณ 10 = องศา) → "
                    f"{direction_text(n) or 'ไม่อยู่ในตาราง'} (ช่อง B)"
                )
        if ff is not None and ff > 0 and dd not in ("00", "//"):
            label = strength_text(knots) or "-"
            if m.iw <= 1:
                lines.append(
                    f"ff={ffs} → {ff} เมตร/วินาที × 1.944 = {ff * 1.944:.1f} → ปัดเป็น {knots} นอต → {label} (ช่อง C)"
                )
            else:
                lines.append(f"ff={ffs} → {ff} นอต → {label} (ช่อง C)")
        elif ffs == "//":
            lines.append("ff=// → ไม่มีค่าความเร็วลม (ช่อง C ว่าง)")
        add(g3, "ลมและเมฆรวม (N dd ff) คือกลุ่มที่ 3 เสมอ", lines, "ลงช่อง B · C · D", "use")

    seven_used = False
    for k, tok in enumerate(sec1):
        if k < 3:
            continue
        if not _FIVE.match(tok):
            add(tok, "กลุ่มข้อมูลอื่น", ["ไม่ใช้ในรายงานนี้"], "ไม่ลงตาราง", "skip")
            continue
        d = tok[0]
        if k == 3 and ffs == "99" and _fm(r"00\d{3}", tok):
            add(
                tok, "ความเร็วลมจริง (เพราะ ff=99)",
                [f"00 = ตัวนำ · fff={tok[2:]} → {int(tok[2:])} " + ("เมตร/วินาที" if m.iw <= 1 else "นอต")],
                "ใช้แทน ff ในช่อง C", "use",
            )
        elif d == "1":
            if _fm(r"1[01]\d{3}", tok):
                add(
                    tok, "อุณหภูมิอากาศ (1 s TTT)",
                    [f"s={tok[1]} → {'ติดลบ' if tok[1] == '1' else 'ค่าบวก'}", f"TTT={tok[2:]} → {_signed(tok)} °C (หารสิบ)"],
                    "ลงช่อง F", "use",
                )
            else:
                add(tok, "อุณหภูมิอากาศ", ["ไม่มีค่า (//)"], "ช่อง F ว่าง", "skip")
        elif d == "2":
            if _fm(r"2[01]\d{3}", tok):
                add(
                    tok, "จุดน้ำค้าง (2 s TdTdTd)",
                    [f"= {_signed(tok)} °C", "จุดน้ำค้างต้องไม่สูงกว่าอุณหภูมิ"],
                    "ใช้ตรวจเท่านั้น", "chk",
                )
            elif _fm(r"29\d{3}", tok):
                add(tok, "ความชื้นสัมพัทธ์", [f"= {int(tok[2:])} %"], "ไม่ลงตาราง", "skip")
            else:
                add(tok, "จุดน้ำค้าง", ["ไม่มีค่า"], "ไม่ลงตาราง", "skip")
        elif d == "3" and _fm(r"3\d{4}", tok):
            add(tok, "ความกดอากาศที่สถานี (3 P0P0P0P0)", [f"= {_pressure(tok[1:])} (ตัดเลขพัน/ร้อยออก)"], "ไม่ลงตาราง", "skip")
        elif d == "4" and _fm(r"4[09]\d{3}", tok):
            add(tok, "ความกดอากาศระดับน้ำทะเล (4 PPPP)", [f"= {_pressure(tok[1:])}"], "ไม่ลงตาราง", "skip")
        elif d == "5" and _fm(r"5[0-8]\d{3}", tok):
            add(
                tok, "แนวโน้มความกดอากาศ 3 ชม. (5 a ppp)",
                [f"a={tok[1]} → {_tendency(int(tok[1]))}", f"ppp={tok[2:]} → {int(tok[2:]) / 10:.1f} hPa"],
                "ไม่ลงตาราง", "skip",
            )
        elif d == "6":
            rr, tr = tok[1:4], tok[4]
            ok = bool(_fm(r"\d{3}|///", rr))
            add(
                tok, "ปริมาณฝน (6 RRR tR)",
                [
                    f"RRR={rr} → {rrr_text(rr) if ok else 'ไม่ทราบ'}",
                    f"tR={tr} → ฝนสะสมในช่วง {tr_label(tr)} ที่ผ่านมา",
                    'ไม่ใช้ค่านี้ลงตาราง ให้ดูช่อง "ปริมาณฝน 3 ชม." ในหน้า METNET',
                ],
                "ไม่ลงตาราง (ใช้ค่าจาก METNET)", "skip",
            )
        elif d == "7":
            if not seven_used:
                seven_used = True
                ws = tok[1:3]
                lines = ["7 = ตัวนำกลุ่มลักษณะอากาศ"]
                has_text = False
                if _fm(r"\d\d", ws):
                    w = int(ws)
                    if w < C.WW_MIN:
                        lines.append(f"ww={ws} น้อยกว่า 04 → ไม่ต้องลงลักษณะอากาศ (ช่อง E ว่าง)")
                    elif w in C.WW:
                        lines.append(f"ww={ws} → {C.WW[w]} (ช่อง E)")
                        has_text = True
                    else:
                        lines.append(f"ww={ws} ไม่อยู่ในตาราง → ช่อง E เป็นช่องแดง ให้เลือกเอง")
                        has_text = True
                else:
                    lines.append(f"ww={ws} → ไม่มีค่า (ช่อง E ว่าง)")
                lines.append(f"W1W2={tok[3:]} = ลักษณะอากาศที่ผ่านมา (ไม่ใช้)")
                add(
                    tok, "ลักษณะอากาศ (7 ww W1W2) ใช้กลุ่ม 7 กลุ่มแรกเท่านั้น", lines,
                    "ลงช่อง E" if has_text else "ช่อง E ว่าง", "use",
                )
            else:
                add(tok, "กลุ่มที่ขึ้นต้นด้วย 7 กลุ่มที่สอง", ["ไม่ใช้ เพราะใช้กลุ่ม 7 กลุ่มแรกเท่านั้น"], "ไม่ลงตาราง", "skip")
        elif d == "8":
            add(
                tok, "เมฆ (8 Nh CL CM CH)",
                [
                    f"Nh={tok[1]} → เมฆชั้นต่ำ/กลาง {tok[1]} ส่วนจาก 8",
                    f"CL={tok[2]} ชนิดเมฆชั้นต่ำ · CM={tok[3]} ชั้นกลาง · CH={tok[4]} ชั้นสูง (/ = มองไม่เห็นหรือไม่รายงาน)",
                ],
                "ไม่ลงตาราง", "skip",
            )
        else:
            add(tok, "กลุ่มข้อมูลอื่น", ["ไม่ใช้ในรายงานนี้"], "ไม่ลงตาราง", "skip")

    for k, tok in enumerate(rest):
        if k == 0:
            add(tok, "เริ่มส่วนที่ 3 (ข้อมูลเพิ่มเติม)", ["กลุ่มหลังจุดนี้ไม่ใช้เลือกลักษณะอากาศ แม้จะขึ้นต้นด้วย 7"], "ไม่ลงตารางทั้งส่วน", "skip")
        elif _fm(r"7\d{4}", tok):
            add(
                tok, "ฝน 24 ชม. (7 RRRR)",
                [f"RRRR={tok[1:]} → {int(tok[1:]) / 10:.1f} มม. (หารสิบ)", "ขึ้นต้นด้วย 7 แต่ไม่ใช่ลักษณะอากาศ"],
                "ไม่ลงตาราง (รอบ 07.00 ใช้ค่าจาก METNET)", "skip",
            )
        elif _fm(r"6[0-9/]{4}", tok):
            rr = tok[1:4]
            ok = bool(_fm(r"\d{3}|///", rr))
            add(tok, "ปริมาณฝน (6 RRR tR)", [f"RRR={rr} → {rrr_text(rr) if ok else 'ไม่ทราบ'}", f"tR={tok[4]} → ช่วง {tr_label(tok[4])}"], "ไม่ลงตาราง", "skip")
        elif _fm(r"5[89]\d{3}", tok):
            add(tok, "ความกดอากาศเปลี่ยนใน 24 ชม. (5 8/9 ppp)", [f"ppp={tok[2:]} → {int(tok[2:]) / 10:.1f} hPa"], "ไม่ลงตาราง", "skip")
        else:
            add(tok, "ข้อมูลเพิ่มเติม", ["ไม่ใช้ในรายงานนี้"], "ไม่ลงตาราง", "skip")
    return items
