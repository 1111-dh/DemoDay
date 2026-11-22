import type { SceneDoc } from "@demoday/contracts";

/** 장면 길이를 비율대로 늘리거나 줄여 totalSec에 맞춘 프레임 수 배열. */
export function fitFrames(doc: SceneDoc): number[] {
  const sum = doc.scenes.reduce((acc, s) => acc + s.durationSec, 0);
  const ratio = doc.totalSec / sum;
  return doc.scenes.map((s) => Math.max(1, Math.round(s.durationSec * ratio * doc.fps)));
}
