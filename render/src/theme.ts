import { staticFile } from "remotion";
import { loadFont } from "@remotion/fonts";

/**
 * Pretendard(OFL, public/fonts/LICENSE.txt)를 파일로 불러온다 — 이름만 쓰면 PC마다 다른 시스템 폰트가 나온다.
 * loadFont가 delayRender로 렌더를 붙잡으므로 첫 프레임부터 같은 글꼴이다.
 */
for (const [weight, name] of [["400", "Regular"], ["500", "Medium"], ["600", "SemiBold"], ["700", "Bold"]]) {
  loadFont({ family: "Pretendard", url: staticFile(`fonts/Pretendard-${name}.woff2`), weight });
}

/** 기준 영상 톤: 밝은 회백색 배경 + 주황 강조. */
export const theme = {
  bg: "#f3f2ee",
  ink: "#1c1c1e",
  sub: "#6b6b70",
  accent: "#f26b1d",
  label: "#111113",
  /** 어두운 장(문제) 배경 */
  night: "#16161a",
  red: "#e0483e",
  green: "#2f9e5b",
  /** 한국어가 단어 중간에서 줄바꿈되지 않고, 끝 단어가 혼자 내려가지 않게 */
  keepAll: { wordBreak: "keep-all" as const, textWrap: "balance" as const },
  font: "Pretendard, sans-serif",
};
