"""ตรวจค่าผิดปกติรายช่อง (ผลลัพธ์ระดับ err = ต้องแก้, warn = เตือน, note = แจ้ง)"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import config as C
from .rain import Rain, expected_h, fmt_tenths, parse_rain, parse_temp
from .schemas import RowIn

RANK = {"note": 1, "warn": 2, "err": 3}
Flags = list[dict[str, dict[str, str]]]


@dataclass
class Context:
    day: Optional[int]  # วันที่ของรายงาน
    round: Optional[int]  # รอบ (ชั่วโมงเวลาไทย)
    prev_list: Optional[list[str]]  # H เดิมเรียงตามสถานี ถ้าใช้ตรวจได้


def time_label(day: int, hour: int) -> str:
    return f"วันที่ {day} · {hour:02d}.00 น."


def compute_flags(rows: list[RowIn], ctx: Context) -> Flags:
    flags: Flags = [{} for _ in rows]

    def put(i: int, col: str, lvl: str, msg: str) -> None:
        cur = flags[i].get(col)
        if cur and RANK[cur["lvl"]] >= RANK[lvl]:
            return
        flags[i][col] = {"lvl": lvl, "msg": msg}

    for i, r in enumerate(rows):
        has = r.has
        if r.problem:
            put(i, "S", "err", r.problem)
        if (
            has and r.msg_time and ctx.day is not None and ctx.round is not None
            and (r.msg_time.day != ctx.day or r.msg_time.hour != ctx.round)
        ):
            put(
                i, "S", "warn",
                f"รหัสข่าวเป็น {time_label(r.msg_time.day, r.msg_time.hour)} "
                f"ต่างจากวันและเวลาของรายงาน ({time_label(ctx.day, ctx.round)})",
            )
        if r.nil:
            put(i, "S", "note", "รหัสข่าวเป็น NIL ไม่มีข้อมูล")
        if has and not r.has_code and not r.nil and not r.problem:
            put(i, "S", "warn", "ยังไม่มีรหัสข่าว ทิศลม กำลังลม ท้องฟ้า และลักษณะอากาศจึงว่างอยู่")

        if r.B == "n/a":
            # n/a คือค่าที่ถูกต้องตามกระดาษเมื่อเครื่องวัดลมเสีย จึงเตือนให้ตรวจ ไม่บล็อกการบันทึก
            put(i, "B", "warn", "ไม่มีค่าทิศลม (//) เครื่องมือเสีย ลง n/a ตามกระดาษ ตรวจแล้วบันทึกได้ หรือเลือกทิศจากรายการ")
        if r.B.startswith("[dd="):
            put(i, "B", "err", f"รหัสทิศลม {r.B[4:-1]} ไม่อยู่ในตาราง")
        if r.E.startswith("[ww="):
            put(i, "E", "err", f"ww {r.E[4:-1]} ไม่อยู่ในตาราง เลือกข้อความจากรายการหรือลบให้ว่าง")

        _check_temperature(i, r, put)
        g, h = parse_rain(r.G), parse_rain(r.H)
        _check_rain_cell(i, "G", g, has, put, big_warning=True)
        _check_rain_cell(i, "H", h, has, put, big_warning=False)
        if ctx.prev_list is not None and h.kind in ("num", "T"):
            _check_accumulation(i, ctx.prev_list[i], g, h, put)
    return flags


def _check_temperature(i: int, r: RowIn, put) -> None:
    t = parse_temp(r.F)
    if t.kind == "bad":
        put(i, "F", "err", "ใส่ตัวเลข เช่น 27.1")
    elif t.kind == "num":
        v = t.tenths or 0
        if v < C.TEMP_MIN_TENTHS or v > C.TEMP_MAX_TENTHS:
            put(i, "F", "warn", f"อุณหภูมิ {fmt_tenths(v)} °C อยู่นอกช่วง 15–40 °C")
        if r.dew is not None and r.dew > v:
            put(i, "F", "warn", f"จุดน้ำค้างในรหัสข่าว ({fmt_tenths(r.dew)}) สูงกว่าอุณหภูมิ ({fmt_tenths(v)})")
        if r.f_syn is not None and r.f_syn != v:
            put(i, "F", "warn", f"ต่างจากอุณหภูมิในรหัสข่าว ({fmt_tenths(r.f_syn)})")


def _check_rain_cell(i: int, col: str, rain: Rain, has: bool, put, big_warning: bool) -> None:
    what = "ฝน 3 ชม." if col == "G" else "ฝนสะสม"
    if rain.kind == "bad":
        extra = " (ทศนิยมใช้จุด ไม่เกิน 1 ตำแหน่ง)" if col == "G" else ""
        put(i, col, "err", f"ค่าฝนต้องเป็นตัวเลข เช่น 0.5 หรือ T หรือ -{extra}")
    elif rain.kind == "dash":
        put(i, col, "note", "ไม่มีค่าฝน (ใช้ -)" if col == "G" else "ไม่มีค่าฝนสะสม (ใช้ -)")
    elif rain.kind == "empty" and has:
        put(i, col, "note", f"ยังไม่กรอกค่า{what}")
    elif big_warning and rain.kind == "num" and (rain.tenths or 0) > C.RAIN_3H_WARN_TENTHS:
        put(i, col, "warn", f"ฝน 3 ชม. {fmt_tenths(rain.tenths or 0)} มม. เกิน 100 มม.")


def _check_accumulation(i: int, old_text: str, g: Rain, h: Rain, put) -> None:
    old = parse_rain(old_text)
    if h.kind == "num" and old.kind == "num" and (h.tenths or 0) < (old.tenths or 0):
        put(i, "H", "err", f"ฝนสะสมน้อยกว่ารอบก่อน (รอบก่อน {fmt_tenths(old.tenths or 0)})")
        return
    ex = expected_h(old, g)
    if ex is None:
        return
    same = (h.kind == "T") if ex.is_trace else (h.kind == "num" and h.tenths == ex.tenths)
    if not same:
        shown = "T" if ex.is_trace else fmt_tenths(ex.tenths)
        put(i, "H", "warn", f"H เดิม {old.show()} + G {g.show()} = {shown} แต่ H = {h.show()}")
