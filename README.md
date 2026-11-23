# DemoDay
2026 경북대학교 컴퓨터학부 해커톤

> 시연을 찍지 마세요, 레포를 넣으세요.
> GitHub 레포 + 배포 URL → 실제 화면 기반 발표용 데모 영상. 기획안: [`docs/기획안.md`](docs/기획안.md)

## 시작 (각자 1회)

```bash
git clone https://github.com/1111-dh/DemoDay.git && cd DemoDay
make setup        # pnpm·uv 의존성, Playwright 크로미움, git 훅 설치, .env 생성
make check        # 통과하면 준비 완료
```
필요: Node 20+, [uv](https://docs.astral.sh/uv/), make. 이후 `.env`에 `ANTHROPIC_API_KEY`를 채웁니다.

## 구조

```
contracts/   JSON Schema 3개 + fixtures  ← 팀 계약. 합의 없이 수정 금지
backend/     A · FastAPI, 레포 분석, LLM
capture/     B · Playwright 캡처
render/      B·C · Remotion 장면/렌더
web/         C · Next.js UI
scripts/     계약 검증, 타입 생성, e2e
```

## 자주 쓰는 명령
`make help`로 전체 목록을 볼 수 있습니다.

| | |
|---|---|
| `make check` | 계약 + 타입 + lint + test 전부 (커밋할 때 자동 실행) |
| `make studio` | Remotion 장면 미리보기 (fixture) |
| `make e2e-render` | fixture → `runs/fixture/preview.mp4` |
| `make e2e REPO=… URL=…` | 전체 파이프라인 |
| `make gen` | 스키마 변경 후 Python/TS 타입 재생성 |

## 웹 영상 회귀 테스트

`make setup` 후 `make e2e-web-video`를 실행합니다. 테스트가 임시 포트에서 웹과 API를 시작하고 종료합니다. 로컬 예제 페이지와 고정된 저장소 분석 자료를 사용하며 `.env`와 API 키는 필요 없습니다. 오프라인에서 실행하려면 Playwright Chromium과 Remotion 브라우저를 미리 설치하세요(`pnpm --filter @demoday/render exec remotion browser ensure`). 렌더러가 사용하는 작업 폴더를 공유하므로 같은 체크아웃에서 다른 영상 렌더와 동시에 실행하지 마세요.

브라우저가 시나리오를 확인하고 원본 영상을 다운로드한 뒤 ‘메인 화면’을 ‘수정한 데모 자막’으로 바꿔 다시 다운로드합니다. 두 MP4에서 화면 장면의 같은 시점을 디코딩하고, 자막 영역의 글자 모양을 별도로 그린 기대 문구와 비교합니다.

매번 출력되는 `runs/video-regression-*/`에 원본·수정본 MP4, 판독 프레임과 기대 글자 이미지가 남습니다. 실패한 경우 `api.log`, `web.log`, 브라우저 오류 당시의 `failure.png` 및 하위 실행 폴더의 `status.json`을 확인하세요. 실패 시점까지 생성된 파일만 남습니다.

## AI 에이전트 하네스

| | Claude Code | Codex |
|---|---|---|
| 규칙 | `CLAUDE.md` → `AGENTS.md` | `AGENTS.md` (루트 + 폴더별) |
| 계약 파일 보호 | 편집 시점에 훅이 차단 | 커밋 시점에 pre-commit이 차단 |
| 수정 직후 검사 | 훅 (ruff / tsc / 스키마) | — (`make check`를 직접 돌리게 AGENTS.md에 명시) |
| 완료 전 검사 | Stop 훅이 `make check` 강제 | pre-commit이 `make check` 강제 |
| 슬래시 명령 | `/e2e`, `/new-scene`, `/contract-change` | AGENTS.md에 같은 절차가 있음 |

**계약 변경 절차:** 팀 채팅에서 합의 → `DEMODAY_CONTRACT_CHANGE=1 claude`(Codex 사용자는 직접 수정) → 스키마 수정 → `make gen` → fixtures 갱신 → `DEMODAY_CONTRACT_CHANGE=1 git commit`.
