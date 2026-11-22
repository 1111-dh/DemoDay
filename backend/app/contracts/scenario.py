# 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class Action(StrEnum):
    goto = 'goto'
    click = 'click'
    type = 'type'
    scroll = 'scroll'
    wait = 'wait'


class Step(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    id: Annotated[int, Field(ge=1)]
    action: Action
    path: Annotated[
        str | None, Field(description='goto일 때 baseUrl 기준 경로. 예: /search')
    ] = None
    selector: Annotated[
        str | None,
        Field(description='Playwright selector. 예: text=검색, input[name=q]'),
    ] = None
    value: Annotated[str | None, Field(description='type일 때 입력값')] = None
    caption: Annotated[str, Field(description='장면 자막 초안')]


class Auth(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    steps: Annotated[list[Step], Field(min_length=1)]


class Scenario(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    baseUrl: Annotated[AnyUrl, Field(description='배포 URL')]
    auth: Annotated[
        Auth | None,
        Field(
            description='캡처 전에 같은 브라우저 컨텍스트에서 한 번 실행하는 로그인. 스크린샷·capture.json·영상에 넣지 않는다. 사용자가 입력하며 LLM은 만들지 않는다. 예: 데모 로그인 URL goto, 또는 로그인 폼 type/click.'
        ),
    ] = None
    steps: Annotated[list[Step], Field(min_length=1)]
