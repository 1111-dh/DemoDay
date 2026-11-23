import type { SceneDoc } from "@demoday/contracts";

/** 장면 길이를 비율대로 늘리거나 줄여 totalSec에 맞춘 프레임 수 배열. */
export function fitFrames(doc: SceneDoc): number[] {
  const sum = doc.scenes.reduce((acc, s) => acc + s.durationSec, 0);
  const ratio = doc.totalSec / sum;
  return doc.scenes.map((s) => Math.max(1, Math.round(s.durationSec * ratio * doc.fps)));
}

/** 장면 전환이 앞 장면과 겹치는 길이(초). */
export const OVERLAP_SEC = 0.3;

/**
 * i번째 장면이 앞 장면과 겹치는 프레임 수(0번은 0). transition "none"이면 0.
 * 짧은 장면에서 양쪽 전환이 장면을 다 먹지 않게 양옆 장면의 절반까지만.
 */
export function overlapFrames(doc: SceneDoc, frames = fitFrames(doc)): number[] {
  return doc.scenes.map((s, i) =>
    i === 0 || s.transition === "none"
      ? 0
      : Math.min(Math.round(OVERLAP_SEC * doc.fps), Math.floor(Math.min(frames[i - 1], frames[i]) / 2)),
  );
}

/** 전환으로 겹친 만큼 줄어든 전체 프레임 수. */
export function totalFrames(doc: SceneDoc): number {
  const frames = fitFrames(doc);
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
  return Math.max(1, sum(frames) - sum(overlapFrames(doc, frames)));
}
