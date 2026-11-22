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
  /**
   * 제목 위 작은 라벨 (예: "01", "문제"). 있으면 장 구분 카드로 그린다
   */
  kicker?: string;
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
  /**
   * caption 안에서 강조할 단어
   */
  highlight?: string[];
  video?: VideoClip;
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
/**
 * 있으면 이 구간을 재생하고, image는 대체 화면(poster)으로 쓴다
 */
export interface VideoClip {
  /**
   * run 디렉터리 기준. 예: capture.webm
   */
  src: string;
  startMs: number;
  endMs: number;
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
