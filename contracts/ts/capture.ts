// 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

/**
 * B(캡처) → A(장면 생성). 단계별 실제 화면 스크린샷과 클릭 좌표. image 경로는 run 디렉터리 기준 상대경로.
 */
export interface Capture {
  viewport: {
    w: number;
    h: number;
  };
  shots: Shot[];
}
export interface Shot {
  stepId: number;
  /**
   * 예: shots/2.png (run 디렉터리 기준)
   */
  image: string;
  /**
   * 클릭 좌표(뷰포트 px). 클릭이 없는 단계는 null
   */
  click: Point | null;
  /**
   * fallback = 셀렉터를 못 찾아 정적 스크린샷으로 대체한 단계
   */
  status?: "ok" | "fallback";
  /**
   * 캡처 시작 기준 화면 전환 시점(ms)
   */
  atMs?: number;
}
export interface Point {
  x: number;
  y: number;
}
