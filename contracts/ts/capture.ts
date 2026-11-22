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
  /**
   * 세션 녹화 파일, run 디렉터리 기준 상대경로 (예: capture.webm). 녹화 실패 시 생략. 로그인 과정은 들어가지 않는다
   */
  video?: string;
  /**
   * 로그인 장면용 정지 화면 (입력칸을 가린 상태). 없으면 로그인 장면 없이 간다
   */
  login?: {
    /**
     * 예: shots/login-1.png (run 디렉터리 기준)
     */
    images: string[];
  };
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
  clip?: Clip;
}
export interface Point {
  x: number;
  y: number;
}
/**
 * 이 단계가 video에서 차지하는 구간(녹화 시작 기준 ms). 동작 시작 ~ 화면 안정 직후
 */
export interface Clip {
  startMs: number;
  endMs: number;
}
