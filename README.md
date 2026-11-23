# DemoDay
2026 경북대학교 컴퓨터학부 해커톤

> 시연을 찍지 마세요, 레포를 넣으세요.

**GitHub 레포 링크와 배포 URL만 넣으면, 실제 서비스 화면을 녹화해 발표용 데모 영상(MP4, 1920×1080)을 만들어 줍니다.**
캡스톤·종합설계 팀이 발표 전에 데모 영상을 만드는 수고를 덜어 주는 서비스예요. 기획안: [`docs/기획안.md`](docs/기획안.md)

## 무엇을 해 주나요

- **레포를 읽고 시연 순서를 짜요.** 라우트·버튼·입력칸·README를 분석해서 어떤 화면을 어떤 순서로 보여줄지 시나리오를 만들어요. React Router, Next.js, Vue Router, Nuxt, SvelteKit, Flutter web을 지원해요.
- **실제 서비스를 직접 써 보며 녹화해요.** 헤드리스 브라우저가 배포 URL에서 클릭·입력·스크롤을 하고 그대로 녹화해요. 테스트 계정을 주면 로그인한 뒤 찍고, 로그인 값은 영상과 로그 어디에도 남기지 않아요.
- **에이전트 녹화 모드 (선택):** AI가 화면을 보면서 다음에 무엇을 누를지 직접 골라 서비스 흐름을 따라가요.
- **화면을 보고 자막을 써요.** 녹화한 화면을 이미지 모델이 읽고, 그 내용으로 해요체 자막과 강조어를 만들어요.
- **이야기가 있는 영상이에요.** README에서 뽑은 문제·해결을 모션 그래픽으로 보여주고, 실제 화면 → 정리 순서로 이어져요. 영상 길이는 내용에 맞추고, 요청한 시간은 최대 길이로만 써요.
- **웹에서 고쳐요.** 시나리오 순서를 바꾸고, 장면 길이·자막을 고친 뒤 다시 렌더할 수 있어요. 영상에 바라는 점(화면 순서, 말투, 강조)을 프롬프트로 넣을 수 있어요.

## 동작 방식

```
레포 + 배포 URL ─[분석·LLM]→ scenario.json ─[Playwright 녹화]→ capture.json + 영상
                                                               │ (이미지 모델이 화면을 읽음)
                          scene.json ←──[LLM 자막·구성]───────┘
                              │
                              └─[Remotion 렌더]→ preview.mp4 (1920×1080)
```

LLM은 영상을 직접 만들지 않아요. 장면 JSON만 만들고, 렌더러가 그 JSON을 그대로 그려요. 그래서 실제 화면과 다른 "가짜 데모"가 나오지 않아요. 단계 사이 형식은 `contracts/*.schema.json`이 정해요.

## 직접 실행하기

```bash
git clone https://github.com/1111-dh/DemoDay.git && cd DemoDay
make setup        # pnpm·uv 의존성, Playwright 크로미움, git 훅 설치, .env 생성
make check        # 통과하면 준비 완료
```
필요: Node 20+, [uv](https://docs.astral.sh/uv/), make.

`.env`에 아래 값을 채운 뒤 실행해요.

```bash
make dev-api      # API  http://localhost:8000
make dev-web      # 웹   http://localhost:3000
# 또는 웹 없이 한 번에:
make e2e REPO=https://github.com/nuxt/movies URL=https://movies.nuxt.space
```

### 환경변수 (`.env`)

| 이름 | 필수 | 설명 |
|---|---|---|
| `LLM_PROVIDER` | 권장 | `baze`(기본 추천) · `groq` · `anthropic` 중 **하나** |
| `BAZE_API_KEY` | `baze`일 때 | BAZE API 게이트웨이 키. 기본 모델은 Claude Haiku 5.5예요(`BAZE_MODEL`, `BAZE_VISION_MODEL`, `BAZE_AGENT_MODEL`로 변경) |
| `GROQ_API_KEY` | 선택 | Groq 키. `baze`가 크레딧·장애로 실패하면 예비로 써요 |
| `ANTHROPIC_API_KEY` | `anthropic`일 때 | Anthropic API 키 |
| `GITHUB_TOKEN` | **권장** | 없으면 GitHub API가 시간당 60회로 막혀서 레포 분석이 실패할 수 있어요 |
| `CAPTURE_MODE` | 선택 | `agent`면 에이전트 녹화 모드로 찍어요(느리고 결과가 매번 달라요) |
| `DEMODAY_API_URL` | 웹 배포 | 웹 서버가 API로 요청을 넘길 주소(기본 `http://127.0.0.1:8000`) |

LLM 키가 없어도 규칙 기반 기본값으로 영상은 나와요(자막이 단순해져요).

### 시연 레포 미리 준비

```bash
make warm          # backend/samples.json의 레포를 미리 분석해 캐시
make warm AGENT=1  # 에이전트로 한 번 녹화해서, 에이전트가 고른 동작을 캐시(시연 때는 그대로 재생)
```
웹 첫 화면의 예시 버튼이 `backend/samples.json`을 읽어요. 같은 레포·URL·프롬프트로 요청하면 캐시에서 바로 나와요.

## 배포

**API 하나가 분석·녹화(크로미움)·렌더(Remotion)를 모두 돌려요.** 메모리 2GB 이상인 서버가 필요하고, 512MB 무료 컨테이너에서는 렌더 중에 멈춰요.

1. 서버에서 위의 `make setup`을 하고 `.env`를 채워요.
2. API를 자동 재시작 없이 띄워요.
   ```bash
   cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. 웹(`web/`, Next.js)은 배포 환경변수에 `DEMODAY_API_URL=<API 주소>`만 넣으면 돼요. 웹 서버가 `/api/runs/*`를 API로 넘겨서 CORS 설정이 필요 없어요.

- 해커톤 기간에는 API를 노트북에서 돌리고 [Cloudflare 무료 터널](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)(`cloudflared tunnel --url http://127.0.0.1:8000`)로 공개했어요. 터널을 다시 켜면 주소가 바뀌니 웹의 `DEMODAY_API_URL`도 바꿔야 해요.
- 자동 배포는 없어요. 배포는 수동으로만 해요.

## 구조

```
contracts/   JSON Schema 3개 + fixtures  ← 팀 계약. 합의 없이 수정 금지
backend/     A · FastAPI, 레포 분석, LLM(시나리오·자막·화면 읽기·에이전트)
capture/     B · Playwright 녹화
render/      B · Remotion 장면·렌더
web/         C · Next.js 웹(입력·시나리오 확인·미리보기·장면 수정)
scripts/     계약 검증, 타입 생성, e2e
```

## 자주 쓰는 명령
`make help`로 전체 목록을 볼 수 있어요.

| | |
|---|---|
| `make check` | 계약 + 타입 + lint + test 전부 (커밋할 때 자동 실행) |
| `make e2e REPO=… URL=… [PROMPT=…]` | 전체 파이프라인. 어느 단계에서 깨지는지 출력 |
| `make warm [AGENT=1]` | 시연 레포 캐시 |
| `make studio` | Remotion 장면 미리보기 (fixture) |
| `make e2e-render` | fixture → `runs/fixture/preview.mp4` |
| `make e2e-web-video` | 웹에서 영상 제작·자막 수정·재렌더 회귀 테스트 |
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
