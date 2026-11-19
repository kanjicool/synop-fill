"""โครงสร้างข้อมูลของ request/response (Pydantic)"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .config import STATIONS

Text = Field(default="", max_length=400)


class MsgTime(BaseModel):
    day: int = Field(ge=1, le=32)
    hour: int = Field(ge=0, le=23)


class RowIn(BaseModel):
    code: str = Field(max_length=10)
    status: Literal["pending", "done", "skipped"] = "pending"
    B: str = Text
    C: str = Text
    D: str = Text
    E: str = Text
    F: str = Text
    G: str = Text
    H: str = Text
    has_code: bool = False
    nil: bool = False
    problem: str = Text
    touched: bool = False
    msg_time: Optional[MsgTime] = None
    f_syn: Optional[int] = None
    dew: Optional[int] = None

    @property
    def has(self) -> bool:
        return self.status == "done"


class RefDate(BaseModel):
    y: int = Field(ge=2000, le=2200)
    m: int = Field(ge=1, le=12)
    d: int = Field(ge=1, le=31)


class PrevIn(BaseModel):
    """ข้อมูลจากไฟล์รอบก่อนที่ผู้ใช้เลือก (ได้จาก /api/prev-file)"""

    h: list[str] = Field(max_length=len(STATIONS))
    round: Optional[int] = None
    date: Optional[str] = None


class CheckIn(BaseModel):
    rows: list[RowIn]
    ref: RefDate
    date_override: Optional[str] = None
    round_override: Optional[int] = None
    prev: Optional[PrevIn] = None

    @field_validator("rows")
    @classmethod
    def _rows_match_stations(cls, rows: list[RowIn]) -> list[RowIn]:
        if [r.code for r in rows] != [s.code for s in STATIONS]:
            raise ValueError("รายการสถานีต้องครบ 21 สถานีและเรียงตามไฟล์ต้นแบบ")
        return rows


class DecodeIn(BaseModel):
    code: str = Field(max_length=10)
    raw: str = Field(default="", max_length=20000)
