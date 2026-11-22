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
   * @minItems 1
   */
  steps: [Step, ...Step[]];
}
