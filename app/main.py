"""synop-fill: FastAPI เสิร์ฟหน้าเว็บและ API (ไม่เก็บสถานะ ไฟล์ที่อัปโหลดประมวลผลในหน่วยความจำแล้วทิ้ง)"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import config as C
from .demo import demo_data
from .decoder import (
    decode_station, explain, find_station_chunk, first_station_chunk, parse_messages,
)
from .excel import TemplateError, build_workbook, read_report
from .filename import clean_filename, content_disposition, parse_iso
from .report import build_report
from .schemas import CheckIn, DecodeIn

APP_NAME = "synop-fill"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บแล้วทำใหม่"})


def _no_cache(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME}


@app.get("/api/config")
def get_config() -> JSONResponse:
    return _no_cache(JSONResponse({
        "stations": [{"code": s.code, "name": s.name, "row": s.row} for s in C.STATIONS],
        "options": C.OPTIONS,
        "rounds": [{"h": h, "utc": C.ROUND_UTC[h]} for h in C.ROUNDS],
        "reference": C.REFERENCE,
        "months": C.MONTHS_TH,
        "h_label_24h": C.H_LABEL_24H,
        "h_label_today": C.H_LABEL_TODAY,
    }))


@app.post("/api/decode")
def decode(data: DecodeIn) -> dict:
    """ถอดรหัสข่าวของสถานีเดียว (ใช้ตอนผู้ใช้วาง/พิมพ์รหัสในหน้ากรอกสถานี)"""
    out = {
        "problem": "", "nil": False, "has_code": False, "msg_time": None,
        "B": "", "C": "", "D": "", "E": "", "F": "", "f_syn": None, "dew": None, "explain": None,
    }
    text = data.raw.strip()
    if not text:
        return out
    parsed = parse_messages(text)
    if parsed.problems:
        out["problem"] = parsed.problems[0]
        return out
    hit = find_station_chunk(parsed, data.code)
    if hit is None:
        other = first_station_chunk(parsed)
        if other:
            st = C.STATION_BY_CODE.get(other[1][0])
            out["problem"] = (
                f"รหัสข่าวนี้เป็นของ {st.name} ({st.code}) ไม่ใช่สถานีนี้" if st
                else f"รหัสข่าวนี้เป็นของสถานี {other[1][0]} ไม่ใช่สถานีนี้ ({data.code})"
            )
        else:
            out["problem"] = f"ไม่พบรหัสสถานี {data.code} ในข้อความ"
        out["explain"] = explain(text, data.code)
        return out
    msg, tokens = hit
    out["msg_time"] = {"day": msg.day, "hour": msg.hour}
    out["explain"] = explain(text, data.code)
    d = decode_station(tokens, msg.iw)
    if d.nil:
        out["nil"] = True
        return out
    out.update(has_code=True, B=d.B, C=d.C, D=d.D, E=d.E, F=d.F, f_syn=d.f_syn, dew=d.dew)
    return out


@app.post("/api/check")
def check(data: CheckIn) -> JSONResponse:
    """สรุปทั้งรายงาน: ช่องที่ต้องดู วัน/รอบล่าสุด ชื่อไฟล์ (ฝั่งเว็บส่งข้อมูลมาทุกครั้ง)"""
    return _no_cache(JSONResponse(build_report(data)))


async def _read_upload(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(422, "รับเฉพาะไฟล์ Excel นามสกุล .xlsx")
    data = await file.read(C.MAX_UPLOAD_BYTES + 1)
    if len(data) > C.MAX_UPLOAD_BYTES:
        raise HTTPException(422, "ไฟล์ใหญ่เกิน 5 MB")
    return data


@app.post("/api/prev-file")
async def prev_file(file: UploadFile = File(...)) -> dict:
    """อ่านไฟล์รอบก่อน: ค่า H เดิมของแต่ละสถานี และวัน/รอบจากหัวรายงาน"""
    data = await _read_upload(file)
    try:
        info = read_report(data)
    except TemplateError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"h": info.h, "round": info.round, "date": info.date, "title": info.title}


@app.post("/api/export")
async def export(
    payload: str = Form(...),
    filename: Optional[str] = Form(None),
    template: Optional[UploadFile] = File(None),
) -> Response:
    """สร้างไฟล์ .xlsx จากข้อมูลที่ผู้ใช้ตรวจแล้ว (ปฏิเสธถ้ายังมีช่องที่ต้องแก้)"""
    try:
        data = CheckIn.model_validate(json.loads(payload))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บแล้วทำใหม่") from exc
    report = build_report(data)
    if report["counts"]["err"] > 0:
        raise HTTPException(422, f"ยังมีช่องที่ต้องแก้ {report['counts']['err']} ช่อง กลับไปแก้ก่อนบันทึกไฟล์")
    if report["round"] is None:
        raise HTTPException(422, "ยังไม่ทราบรอบของรายงาน เลือกรอบก่อนบันทึกไฟล์")
    if template is not None and template.filename:
        template_bytes = await _read_upload(template)
    else:
        template_bytes = C.TEMPLATE_PATH.read_bytes()
    values = [{c: getattr(r, c) for c in "BCDEFGH"} for r in data.rows]
    try:
        out = build_workbook(template_bytes, values, report["round"], parse_iso(report["date"]))
    except TemplateError as exc:
        raise HTTPException(422, str(exc)) from exc
    name = clean_filename(filename) or report["filename"]
    headers = {"Content-Disposition": content_disposition(name), "Cache-Control": "no-store"}
    return Response(content=out, media_type=XLSX_TYPE, headers=headers)


@app.get("/")
def index() -> FileResponse:
    return _no_cache(FileResponse(C.WEB_DIR / "index.html"))  # type: ignore[return-value]


if C.WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=C.WEB_DIR), name="static")


@app.get("/api/demo")
def demo() -> JSONResponse:
    """ข้อมูลตัวอย่างสำหรับฝึกใช้ (รอบ 13.00 น. 18-11-69)"""
    return _no_cache(JSONResponse(demo_data()))
