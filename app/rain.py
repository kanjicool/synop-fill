"""อ่านและเปรียบเทียบค่าฝน (ตัวเลข / T / -) ด้วยจำนวนเต็มหน่วยหนึ่งส่วนสิบ มม.

ไม่ใช้ float เพื่อไม่ให้ 0.1 + 0.2 กลายเป็น 0.30000000000000004
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

Kind = Literal["empty", "dash", "T", "num", "bad"]

_NUM = re.compile(r"^(\d{1,4})(?:\.(\d))?$", re.ASCII)
_TEMP = re.compile(r"^(-?)(\d{1,2})(?:\.(\d))?$", re.ASCII)


@dataclass(frozen=True)
class Rain:
    kind: Kind
    tenths: Optional[int] = None  # เฉพาะ kind == "num"

    def show(self) -> str:
        if self.kind == "T":
            return "T"
        if self.kind == "num":
            return fmt_tenths(self.tenths or 0)
        return "-"


def fmt_tenths(t: int) -> str:
    """12 -> '1.2', -5 -> '-0.5'"""
    sign = "-" if t < 0 else ""
    t = abs(t)
    return f"{sign}{t // 10}.{t % 10}"


def parse_rain(value: object) -> Rain:
    v = "" if value is None else str(value).strip()
    if v == "":
        return Rain("empty")
    if v == "-":
        return Rain("dash")
    if v.upper() == "T":
        return Rain("T")
    m = _NUM.match(v)
    if not m:
        return Rain("bad")
    return Rain("num", int(m.group(1)) * 10 + int(m.group(2) or 0))


def parse_temp(value: object) -> Rain:
    """อุณหภูมิใช้ชนิดเดียวกับฝน แต่ติดลบได้ (kind == 'num' / 'empty' / 'bad')"""
    v = "" if value is None else str(value).strip()
    if v == "":
        return Rain("empty")
    m = _TEMP.match(v)
    if not m:
        return Rain("bad")
    mag = int(m.group(2)) * 10 + int(m.group(3) or 0)
    return Rain("num", -mag if m.group(1) else mag)


@dataclass(frozen=True)
class Expected:
    tenths: int
    is_trace: bool  # ผลรวมเป็น 0 แต่มี T อยู่ -> แสดงเป็น T


def expected_h(old: Rain, g: Rain) -> Optional[Expected]:
    """H ที่ควรเป็น = H เดิม + G โดยถือว่า T = 0 แต่ถ้าผลรวมเป็น 0 และมี T อยู่ให้เป็น T"""
    if old.kind not in ("num", "T") or g.kind not in ("num", "T"):
        return None
    total = (old.tenths or 0 if old.kind == "num" else 0) + (g.tenths or 0 if g.kind == "num" else 0)
    has_trace = old.kind == "T" or g.kind == "T"
    return Expected(total, total == 0 and has_trace)


_TR_LABEL = {
    "1": "6 ชม.", "2": "12 ชม.", "3": "18 ชม.", "4": "24 ชม.", "5": "1 ชม.",
    "6": "2 ชม.", "7": "3 ชม.", "8": "9 ชม.", "9": "15 ชม.",
}


def tr_label(tr: str) -> str:
    return _TR_LABEL.get(tr, "ไม่ทราบ")


def rrr_text(rrr: str) -> str:
    """แปลงปริมาณฝนในกลุ่ม 6RRRtR เป็นข้อความ (ใช้ในคำอธิบายรหัส)"""
    if rrr == "///":
        return "ไม่ได้วัดหรือค่าเสีย"
    n = int(rrr)
    if n <= 988:
        return f"{n} มม."
    if n == 989:
        return "989 มม. ขึ้นไป"
    if n == 990:
        return "ฝนน้อยกว่าจะวัดได้ (T)"
    return f"{(n - 990) / 10:.1f} มม."
