# render/ — B 담당 (Remotion), 아키텍처 장면은 C

- 미리보기: `make studio`(fixture scene.json 사용). 렌더: `pnpm --filter @demoday/render render <runDir> <out.mp4> [--scale=0.5]`. 빠른 확인은 `make e2e-render`.
- Remotion API는 버전마다 다르므로 기억에 의존하지 말고 `node_modules/remotion`의 타입이나 공식 문서를 확인한다.
- 구조: `src/Root.tsx`(Composition), `src/Demo.tsx`(장면 type별 분기, Series), `src/timing.ts`(totalSec에 맞춰 길이 조정), `src/scenes/*Scene.tsx`.
- 이미지는 `staticFile(\`run/${scene.image}\`)`로 읽는다. 렌더 스크립트(`render.mjs`)는 렌더마다 임시 폴더에 자기 public(글꼴·`bgm.mp3` + scene.json이 가리키는 이미지·녹화만)을 만들어 `--public-dir`로 넘기고 끝나면 그 폴더만 지운다 — 동시 렌더가 서로 덮지 않고, `scenario.json`(로그인 값) 등은 정적 자료에 들어가지 않는다(#56). run 밖을 가리키는 경로는 복사하지 않는다. studio(`use-run.mjs`)만 공용 `public/run`을 쓴다. 자체 검사: `node scripts/use-run.check.mjs`.
- 장면 컴포넌트는 **props(scene)만으로 결정적으로** 그린다. `Math.random`, `Date.now`, 네트워크 호출은 금지하고 애니메이션은 `useCurrentFrame`과 `interpolate`/`spring`으로 만든다.
- 좌표(zoom, cursor)는 캡처 viewport 1280x720 기준 px이고, Composition도 1280x720이다.
- 새 장면 type 추가 순서: (팀 합의) 스키마 → `make gen` → `src/scenes/XScene.tsx` → `Demo.tsx`의 switch에 case 추가 → fixture에 예시 추가 → `make check`. switch는 `never` 검사를 하므로 case를 빼먹으면 typecheck가 실패한다.
- 공통 모션은 `src/motion.tsx`(움직이는 배경 `Backdrop`, 단어별로 올라오는 `Words`, 라벨 `Pill`). 화면 장면의 레이아웃(center·split·tilt·wide)과 카메라(다가가기·물러나기·훑기)는 화면 내용으로 고른다(`pickLayouts`: 클릭 → 클로즈업, 핵심 영역 → 3D 기울기, 둘러보기 → 넓게 훑기, 연달아 같은 연출 금지). 문제 장면은 `ProblemStory`가 아이콘별 가상 인터넷 화면(메신저·로딩·검색·대시보드·단톡방)으로 그린다(11/24 피드백).
- 장면 전환은 `TransitionSeries`로 앞 장면과 0.3초 겹친다(`timing.ts`의 `overlapFrames`/`totalFrames`). 전체 길이는 겹친 만큼 줄어든다. 글꼴은 `public/fonts`의 Pretendard(OFL)를 `theme.ts`에서 `loadFont`로 불러온다 — 시스템 폰트 이름만 쓰지 않는다.
