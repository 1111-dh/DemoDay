# render/ — B 담당 (Remotion), 아키텍처 장면은 C

- 미리보기: `make studio`(fixture scene.json 사용). 렌더: `pnpm --filter @demoday/render render <runDir> <out.mp4> [--scale=0.5]`. 빠른 확인은 `make e2e-render`.
- Remotion API는 버전마다 다르므로 기억에 의존하지 말고 `node_modules/remotion`의 타입이나 공식 문서를 확인한다.
- 구조: `src/Root.tsx`(Composition), `src/Demo.tsx`(장면 type별 분기, Series), `src/timing.ts`(totalSec에 맞춰 길이 조정), `src/scenes/*Scene.tsx`.
- 이미지는 `staticFile(\`run/${scene.image}\`)`로 읽는다. 렌더 스크립트(`render.mjs`)는 렌더마다 임시 폴더에 자기 public(글꼴·`bgm.mp3` + scene.json이 가리키는 이미지·녹화만)을 만들어 `--public-dir`로 넘기고 끝나면 그 폴더만 지운다 — 동시 렌더가 서로 덮지 않고, `scenario.json`(로그인 값) 등은 정적 자료에 들어가지 않는다(#56). run 밖을 가리키는 경로는 복사하지 않는다. studio(`use-run.mjs`)만 공용 `public/run`을 쓴다. 자체 검사: `node scripts/use-run.check.mjs`.
- 장면 컴포넌트는 **props(scene)만으로 결정적으로** 그린다. `Math.random`, `Date.now`, 네트워크 호출은 금지하고 애니메이션은 `useCurrentFrame`과 `interpolate`/`spring`으로 만든다.
- 좌표(zoom, cursor)는 캡처 viewport 1280x720 기준 px이고, Composition도 1280x720이다.
- 새 장면 type 추가 순서: (팀 합의) 스키마 → `make gen` → `src/scenes/XScene.tsx` → `Demo.tsx`의 switch에 case 추가 → fixture에 예시 추가 → `make check`. switch는 `never` 검사를 하므로 case를 빼먹으면 typecheck가 실패한다.
- 계약 밖 렌더 전용 prop: `domain`(주소창), `logo`(backend `app/logo.py`가 배포 사이트에서 받은 run의 `logo.*` — `render.mjs`가 복사해 넘기고, 연결("하지만")·마무리("정리") 카드와 제목에 넣는다).
- 공통 모션은 `src/motion.tsx`(움직이는 배경 `Backdrop`, 단어별로 올라오는 `Words`, 라벨 `Pill`). 화면 장면의 레이아웃(center·split·tilt·wide)과 카메라(다가가기·물러나기·훑기)는 화면 내용으로 고른다(`pickLayouts`: 클릭 → 클로즈업, 핵심 영역 → 3D 기울기, 둘러보기 → 넓게 훑기, 연달아 같은 연출 금지). 문제 장면은 `ProblemStory`가 상황마다 가상 인터넷 화면 11가지(메신저·로딩·검색·대시보드·단톡방·캘린더 충돌·스프레드시트 수작업·청구서·오류 페이지·지도·답안 시간 초과) 중 하나로 그린다. 상황 문장의 단어로 먼저 고르고(`pickKinds`의 `WORDS`), 없으면 아이콘으로, **한 장면 안에서 같은 화면은 두 번 쓰지 않는다**. 핵심 연출은 1.5초 안에 끝나게 둔다(상황당 길이가 줄어도 잘리지 않게). 마무리 카드(kicker "정리")에 `subtitle`(서비스 이름)이 있으면 엔딩 배치 — [로고][서비스 이름] 한 줄 + 아래 "이제, ~하세요" 문장(`text`).
- 장면 전환은 `TransitionSeries`로 앞 장면과 0.3초 겹친다(`timing.ts`의 `overlapFrames`/`totalFrames`). 전체 길이는 겹친 만큼 줄어든다. 글꼴은 `public/fonts`의 Pretendard(OFL)를 `theme.ts`에서 `loadFont`로 불러온다 — 시스템 폰트 이름만 쓰지 않는다.
