// 자동 생성 파일 — 수정 금지. make gen 으로 재생성.

export type Transition = "none" | "fade" | "slide";

/**
 * A(장면 생성) → B(렌더링), C(미리보기·수정). LLM은 영상이 아니라 이 JSON만 만든다.
 */
export interface SceneDoc {
  fps: 24 | 30 | 60;
  /**
   * 목표 발표 시간(초). 렌더 시 장면 길이를 이 비율로 맞춘다
   */
  totalSec: number;
  /**
   * @minItems 1
   */
  scenes: [TitleScene | ScreenScene | ArchitectureScene, ...(TitleScene | ScreenScene | ArchitectureScene)[]];
}
export interface TitleScene {
  type: "title";
  durationSec: number;
  transition?: Transition;
  text: string;
  subtitle?: string;
}
export interface ScreenScene {
  type: "screen";
  durationSec: number;
  transition?: Transition;
  /**
   * run 디렉터리 기준 상대경로. 예: shots/2.png
   */
  image: string;
  zoom?: Zoom;
  cursor?: Point;
  caption?: string;
}
export interface Zoom {
  x: number;
  y: number;
  scale: number;
}
export interface Point {
  x: number;
  y: number;
}
export interface ArchitectureScene {
  type: "architecture";
  durationSec: number;
  transition?: Transition;
  /**
   * @minItems 1
   */
  nodes: [string, ...string[]];
  /**
   * [from, to] — nodes 배열 인덱스
   */
  edges: [number, number][];
}
