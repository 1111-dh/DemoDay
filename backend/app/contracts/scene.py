# 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Fps(IntEnum):
    integer_24 = 24
    integer_30 = 30
    integer_60 = 60


class Transition(StrEnum):
    none = 'none'
    fade = 'fade'
    slide = 'slide'


class Point(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    x: float
    y: float


class VideoClip(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    src: Annotated[str, Field(description='run 디렉터리 기준. 예: capture.webm')]
    startMs: Annotated[int, Field(ge=0)]
    endMs: Annotated[int, Field(ge=0)]


class Zoom(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    x: float
    y: float
    scale: Annotated[float, Field(ge=1.0, le=4.0)]


class TitleScene(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    type: Literal['title']
    durationSec: Annotated[float, Field(gt=0.0)]
    transition: Transition | None = 'fade'
    text: str
    subtitle: str | None = None
    kicker: Annotated[
        str | None,
        Field(
            description='제목 위 작은 라벨 (예: "01", "문제"). 있으면 장 구분 카드로 그린다'
        ),
    ] = None


class ScreenScene(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    type: Literal['screen']
    durationSec: Annotated[float, Field(gt=0.0)]
    transition: Transition | None = 'fade'
    image: Annotated[
        str, Field(description='run 디렉터리 기준 상대경로. 예: shots/2.png')
    ]
    zoom: Zoom | None = None
    cursor: Point | None = None
    caption: str | None = None
    highlight: Annotated[
        list[str] | None, Field(description='caption 안에서 강조할 단어')
    ] = None
    video: VideoClip | None = None


class EdgeItem(RootModel[int]):
    root: Annotated[int, Field(ge=0)]


class Edge(RootModel[list[EdgeItem]]):
    root: Annotated[list[EdgeItem], Field(max_length=2, min_length=2)]


class ArchitectureScene(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    type: Literal['architecture']
    durationSec: Annotated[float, Field(gt=0.0)]
    transition: Transition | None = 'fade'
    nodes: Annotated[list[str], Field(min_length=1)]
    edges: Annotated[list[Edge], Field(description='[from, to] — nodes 배열 인덱스')]


class SceneDoc(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    fps: Fps
    totalSec: Annotated[
        float,
        Field(
            description='목표 발표 시간(초). 렌더 시 장면 길이를 이 비율로 맞춘다',
            gt=0.0,
        ),
    ]
    scenes: Annotated[
        list[TitleScene | ScreenScene | ArchitectureScene], Field(min_length=1)
    ]
