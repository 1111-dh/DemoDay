// 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

export type Step = {
  [k: string]: unknown;
} & {
  [k: string]: unknown;
} & {
  [k: string]: unknown;
} & {
  id: number;
  action: "goto" | "click" | "type" | "scroll" | "wait";
  /**
   * goto일 때 baseUrl 기준 경로. 예: /search
   */
  path?: string;
  /**
   * Playwright selector. 예: text=검색, input[name=q]
   */
  selector?: string;
  /**
   * type일 때 입력값
   */
  value?: string;
  /**
   * 장면 자막 초안
   */
  caption: string;
} & {
  id: number;
  action: "goto" | "click" | "type" | "scroll" | "wait";
  /**
   * goto일 때 baseUrl 기준 경로. 예: /search
   */
  path?: string;
  /**
   * Playwright selector. 예: text=검색, input[name=q]
   */
  selector?: string;
  /**
   * type일 때 입력값
   */
  value?: string;
  /**
   * 장면 자막 초안
   */
  caption: string;
} & {
  id: number;
  action: "goto" | "click" | "type" | "scroll" | "wait";
  /**
   * goto일 때 baseUrl 기준 경로. 예: /search
   */
  path?: string;
  /**
   * Playwright selector. 예: text=검색, input[name=q]
   */
  selector?: string;
  /**
   * type일 때 입력값
   */
  value?: string;
  /**
   * 장면 자막 초안
   */
  caption: string;
} & {
  id: number;
  action: "goto" | "click" | "type" | "scroll" | "wait";
  /**
   * goto일 때 baseUrl 기준 경로. 예: /search
   */
  path?: string;
  /**
   * Playwright selector. 예: text=검색, input[name=q]
   */
  selector?: string;
  /**
   * type일 때 입력값
   */
  value?: string;
  /**
   * 장면 자막 초안
   */
  caption: string;
};

/**
 * A(분석) → B(캡처). 헤드리스 브라우저가 따라갈 시연 단계 목록.
 */
export interface Scenario {
  /**
   * 배포 URL
   */
  baseUrl: string;
  /**
   * 캡처 전에 같은 브라우저 컨텍스트에서 한 번 실행하는 로그인. 스크린샷·capture.json·영상에 넣지 않는다. 사용자가 입력하며 LLM은 만들지 않는다. 예: 데모 로그인 URL goto, 또는 로그인 폼 type/click.
   */
  auth?: {
    /**
     * @minItems 1
     */
    steps: [Step, ...Step[]];
  };
  /**
   * @minItems 1
   */
  steps: [Step, ...Step[]];
}
