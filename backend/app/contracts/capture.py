# 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Viewport(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    w: Annotated[int, Field(ge=1)]
    h: Annotated[int, Field(ge=1)]


class Point(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    x: float
    y: float


class Status(StrEnum):
    ok = 'ok'
    fallback = 'fallback'


class Shot(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    stepId: Annotated[int, Field(ge=1)]
    image: Annotated[str, Field(description='예: shots/2.png (run 디렉터리 기준)')]
    click: Annotated[
        Point | None, Field(description='클릭 좌표(뷰포트 px). 클릭이 없는 단계는 null')
    ]
    status: Annotated[
        Status | None,
        Field(description='fallback = 셀렉터를 못 찾아 정적 스크린샷으로 대체한 단계'),
    ] = 'ok'
    atMs: Annotated[
        int | None, Field(description='캡처 시작 기준 화면 전환 시점(ms)', ge=0)
    ] = None


class Capture(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    viewport: Viewport
    shots: list[Shot]
