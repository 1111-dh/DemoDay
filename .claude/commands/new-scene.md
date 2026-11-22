---
description: Remotion 장면 type 추가 (스키마 합의 후)
argument-hint: <scene-type> <설명>
---
새 장면 type을 추가한다: $ARGUMENTS

1. 먼저 `contracts/scene.schema.json`에 이 type이 이미 있는지 확인한다. 없으면 **멈추고** 추가할 스키마 초안을 보여준 뒤 팀 합의를 요청한다(계약 파일은 훅이 막는다).
2. 스키마에 이미 있으면 `render/AGENTS.md`의 "새 장면 type 추가 순서"를 그대로 따른다.
3. `make e2e-render`로 fixture가 렌더되는지 확인하고, `make check`가 통과하면 끝낸다.
