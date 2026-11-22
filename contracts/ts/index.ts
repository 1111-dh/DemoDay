// 계약 타입 진입점. 타입 정의는 make gen 으로 생성된 파일에서 온다.
export type { Scenario, Step } from "./scenario";
export type { Capture, Shot, Point as CapturePoint } from "./capture";
export type {
  SceneDoc,
  TitleScene,
  ScreenScene,
  ArchitectureScene,
  Transition,
  Zoom,
  Point,
} from "./scene";
export type Scene = import("./scene").SceneDoc["scenes"][number];
