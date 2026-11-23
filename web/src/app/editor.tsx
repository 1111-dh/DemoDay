import type { Scene, SceneDoc } from "@demoday/contracts";
import Image from "next/image";
import { useState } from "react";

function caption(s: Scene) {
  switch (s.type) {
    case "screen":
      return s.caption || "";
    case "points":
      return s.heading;
    case "title":
      return s.text;
    default:
      return "아키텍처";
  }
}
const names = {
  title: "제목",
  screen: "화면 캡처",
  points: "핵심 포인트",
  architecture: "아키텍처",
};

function Still({
  s,
  files,
  large = false,
}: {
  s: Scene;
  files: string;
  large?: boolean;
}) {
  return (
    <span className={"still" + (large ? " large" : "")}>
      {s.type === "screen" && files ? (
        <Image
          unoptimized
          src={files + s.image}
          alt=""
          width={640}
          height={360}
        />
      ) : (
        <strong>{caption(s) || names[s.type]}</strong>
      )}
      {large && s.type === "screen" && (
        <span className="subtitle">{s.caption}</span>
      )}
    </span>
  );
}
export default function Editor({
  initial,
  files,
  busy,
  save,
  back,
}: {
  initial: SceneDoc;
  files: string;
  busy: boolean;
  save: (doc: SceneDoc) => void;
  back: () => void;
}) {
  const [doc, setDoc] = useState(initial);
  const [index, select] = useState(0);
  const s = doc.scenes[index];
  function update(next: Scene) {
    const scenes = doc.scenes.map((v, i) =>
      i === index ? next : v,
    ) as SceneDoc["scenes"];
    setDoc({
      ...doc,
      scenes,
      totalSec:
        next.durationSec === s.durationSec
          ? doc.totalSec
          : Math.round(
              (doc.totalSec + next.durationSec - s.durationSec) * 1000,
            ) / 1000,
    });
  }
  function move(delta: number) {
    const target = index + delta;
    const scenes = [...doc.scenes] as SceneDoc["scenes"];
    [scenes[index], scenes[target]] = [scenes[target], scenes[index]];
    setDoc({ ...doc, scenes });
    select(target);
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save(doc);
      }}
    >
      <fieldset disabled={busy} className="editor">
        <aside className="panel">
          <h2>장면 목록</h2>
          <small>{doc.scenes.length}개 장면</small>
          {doc.scenes.map((item, i) => (
            <button
              key={i}
              type="button"
              className="scene-row"
              aria-pressed={index === i}
              onClick={() => select(i)}
            >
              <Still s={item} files={files} />
              <span>
                <small>
                  {String(i + 1).padStart(2, "0")} · {names[item.type]}
                </small>
                <b>{caption(item) || names[item.type]}</b>
                <small>{Number(item.durationSec.toFixed(2))}초</small>
              </span>
            </button>
          ))}
        </aside>
        <section className="panel">
          <h2>
            {index + 1}. {names[s.type]}
          </h2>
          <Still s={s} files={files} large />
          {s.type !== "architecture" && (
            <label>
              {s.type === "points" ? "포인트 제목" : "자막"}
              <input
                value={caption(s)}
                maxLength={s.type === "points" ? 28 : 160}
                onChange={(e) => {
                  const v = e.target.value;
                  update(
                    s.type === "points"
                      ? { ...s, heading: v }
                      : s.type === "title"
                        ? { ...s, text: v }
                        : { ...s, caption: v },
                  );
                }}
              />
            </label>
          )}
          <label>
            장면 길이 (초)
            <input
              type="number"
              min="0.001"
              step="any"
              required
              value={s.durationSec || ""}
              onChange={(e) =>
                update({ ...s, durationSec: Number(e.target.value) })
              }
            />
          </label>
          <button type="button" disabled={!index} onClick={() => move(-1)}>
            ↑ 앞으로
          </button>
          <button
            type="button"
            disabled={index === doc.scenes.length - 1}
            onClick={() => move(1)}
          >
            ↓ 뒤로
          </button>
          <div className="actions">
            <button type="button" onClick={back}>
              돌아가기
            </button>
            {files && (
              <button
                className="primary"
                disabled={
                  doc.totalSec <= 0 ||
                  doc.scenes.some((item) => item.durationSec <= 0)
                }
              >
                {busy ? "저장 중…" : "저장하고 다시 렌더링"}
              </button>
            )}
          </div>
        </section>
      </fieldset>
    </form>
  );
}
