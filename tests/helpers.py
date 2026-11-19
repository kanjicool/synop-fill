"""ตัวช่วยสำหรับเทสต์ (ใช้ตัวสร้างรหัสข่าวสมมติจาก app.demo)"""
from __future__ import annotations

from app import config as C
from app.demo import make_chunk, make_message  # noqa: F401

REAL_48552 = "AAXX 17094\n48552 32460 60504 10311 20255 30088 40094 57006 81246\n333 58014"
REAL_48568 = (
    "AAXX 18064\n48568 01460 81003 10271 20239 30119 40127 57016 60051 70262 8387/\n"
    "333 58019 60056 70270"
)


def station_names() -> list[str]:
    return [s.name for s in C.STATIONS]
