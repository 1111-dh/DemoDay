---
description: 전체 파이프라인을 돌리고 깨진 단계를 진단
argument-hint: <github-repo-url> <deploy-url> [seconds]
---
`make e2e REPO=<첫 인자> URL=<둘째 인자> SEC=<셋째 인자, 없으면 60>`을 실행하라. 인자: $ARGUMENTS

- 성공하면 `runs/<id>/preview.mp4` 경로와 장면 수를 보고한다.
- 실패하면 어느 단계(analyze/capture/scene/render)가 깨졌는지, 그 단계의 담당자(A/B/C, 루트 AGENTS.md 표 참고), 계약 위반인지 구현 버그인지를 짧게 보고한다.
- 내 담당 폴더의 문제가 아니면 고치지 말고 담당자에게 전할 내용만 정리한다.
