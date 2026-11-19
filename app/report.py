"""สรุปรายงานจากข้อมูลทุกสถานี: วัน/รอบล่าสุด ชื่อไฟล์ รายการที่ต้องดู จำนวนคำเตือน

ระบบไม่เก็บสถานะ ฝั่งเว็บส่งข้อมูลทั้งหมดมาทุกครั้งแล้วรับผลสรุปกลับไป
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from . import config as C
from .filename import header_text, make_filename, parse_iso
from .schemas import CheckIn, RowIn
from .validator import Context, compute_flags, time_label

# (รอบของไฟล์รอบก่อน, รอบปัจจุบัน) ที่ใช้ตรวจ H เดิม + G ได้
PREV_PAIRS = {(10, 13), (13, 16)}
COL_LABEL = {"S": "สถานี", "B": "ทิศลม", "C": "กำลังลม", "D": "ท้องฟ้า", "E": "ลักษณะอากาศ", "F": "อุณหภูมิ", "G": "ฝน 3 ชม."}


def h_label(round_: Optional[int]) -> str:
    return C.H_LABEL_24H if round_ == 7 else C.H_LABEL_TODAY


def footnote(round_: Optional[int]) -> str:
    return C.NOTE_24H if round_ == 7 else C.NOTE_TODAY


def _latest(rows: list[RowIn]) -> Optional[tuple[int, int, str, int]]:
    """(วัน, ชั่วโมง, ชื่อสถานีแรกที่ส่งเวลานี้, จำนวนสถานีที่ส่งเวลานี้)"""
    # นับสถานีที่กำลังกรอกอยู่ด้วย (ยังไม่กดถัดไป) เพื่อให้รู้รอบตั้งแต่สถานีแรก
    cands = [
        (r.msg_time.day, r.msg_time.hour, C.STATION_BY_CODE[r.code].name)
        for r in rows if r.msg_time and r.status != "skipped" and not r.problem
    ]
    if not cands:
        return None
    days = [c[0] for c in cands]
    wrap = (max(days) - min(days)) > 20  # ข้ามเดือน เช่น 31 กับ 1

    def key(c: tuple[int, int, str]) -> int:
        return ((c[0] + 31) if (wrap and c[0] < 15) else c[0]) * 24 + c[1]

    best = max(cands, key=key)
    return best[0], best[1], best[2], sum(1 for c in cands if (c[0], c[1]) == (best[0], best[1]))


def _date(latest: Optional[tuple[int, int, str, int]], data: CheckIn) -> dt.date:
    override = parse_iso(data.date_override)
    if override:
        return override
    y, m, d = data.ref.y, data.ref.m, data.ref.d
    day = latest[0] if latest else d
    if latest and latest[0] - d > 15:  # ข้อความเป็นของเดือนก่อน
        m -= 1
        if m < 1:
            m, y = 12, y - 1
    if day >= 32:  # UTC วันที่ 31 หลัง 17.00 น. กลายเป็นวันที่ 1 ของเดือนถัดไปตามเวลาไทย
        day = 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    for _ in range(3):  # วันที่ที่ไม่มีในเดือนนั้น (เช่น 31 ในเดือนที่มี 30 วัน) ถอยไปเดือนก่อน
        try:
            return dt.date(y, m, day)
        except ValueError:
            m -= 1
            if m < 1:
                m, y = 12, y - 1
    return dt.date(data.ref.y, data.ref.m, min(d, 28))


def build_report(data: CheckIn) -> dict:
    rows = data.rows
    latest = _latest(rows)
    day = _date(latest, data)
    round_auto = latest[1] if latest and latest[1] in C.ROUNDS else None
    round_ = data.round_override if data.round_override in C.ROUNDS else round_auto

    prev_list: Optional[list[str]] = None
    prev_note: Optional[str] = None
    if data.prev and len(data.prev.h) == len(rows):
        prev_day = parse_iso(data.prev.date)
        if data.prev.round is not None and round_ is not None and (data.prev.round, round_) in PREV_PAIRS \
                and (prev_day is None or prev_day == day):
            prev_list = data.prev.h
        elif round_ in (13, 16):
            prev_note = (
                f"ไฟล์ต้นแบบที่เลือกไม่ใช่รอบก่อนหน้าของรอบ {round_:02d}.00 น. ของวันเดียวกัน "
                "จึงข้ามการตรวจฝนสะสม"
            )

    ctx = Context(day.day, round_, prev_list)
    flags = compute_flags(rows, ctx)

    label = h_label(round_)
    names = {**COL_LABEL, "H": label.replace(" (มม.)", "")}
    items: list[dict] = []
    counts = {"err": 0, "warn": 0, "note": 0}
    for i, f in enumerate(flags):
        for col, flag in f.items():
            counts[flag["lvl"]] += 1
            items.append({
                "lvl": flag["lvl"], "row": i, "col": col,
                "text": f"{C.STATIONS[i].name} · {names[col]}: {flag['msg']}",
            })
    glob: list[dict] = []
    if round_ is None:
        glob.append({"lvl": "warn", "row": -1, "col": "", "text": "ยังไม่ทราบรอบของรายงาน (ไม่มีรหัสข่าวที่บอกเวลา) เลือกรอบในขั้นบันทึกไฟล์"})
    if prev_note:
        glob.append({"lvl": "note", "row": -1, "col": "", "text": prev_note})
    order = {"err": 0, "warn": 1, "note": 2}
    issues = sorted(glob + items, key=lambda x: order[x["lvl"]])

    missing = [C.STATIONS[i].name for i, r in enumerate(rows) if not r.has]
    return {
        "flags": flags,
        "latest": {"day": latest[0], "hour": latest[1], "from": latest[2], "count": latest[3]} if latest else None,
        "date": day.isoformat(),
        "day": day.day,
        "round": round_,
        "round_auto": round_auto,
        "prev_list": prev_list,
        "prev_note": prev_note,
        "h_label": label,
        "footnote": footnote(round_),
        "title_text": header_text(day, round_),
        "filename": make_filename(round_, day),
        "issues": issues,
        "counts": counts,
        "global_warn": sum(1 for g in glob if g["lvl"] == "warn"),
        "filled": len(rows) - len(missing),
        "missing": missing,
        "latest_text": time_label(latest[0], latest[1]) if latest else None,
    }
