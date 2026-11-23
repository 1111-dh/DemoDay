"use client";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Scenario, Scene, SceneDoc } from "@demoday/contracts";
import Image from "next/image";
import videoFixture from "@demoday/contracts/fixtures/scene.video.json";
import fixture from "@demoday/contracts/fixtures/scene.json";

const titles = ["프로젝트 입력", "시나리오 확인", "영상 미리보기", "장면 수정"];
const stages: Record<string, string> = {
  queued: "제작 대기 중",
  capturing: "웹 화면 캡처 중",
  scening: "장면 구성 중",
  rendering: "영상 렌더링 중",
};
async function request(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
) {
  const response = await fetch("/api/runs" + path, {
    method,
    signal,
    cache: "no-store",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail
            .map((item: string | { msg: string }) =>
              typeof item === "string" ? item : item.msg,
            )
            .join(" · ")
        : typeof data.detail === "string"
          ? data.detail +
            (response.status === 400 && data.detail.includes("로그인")
              ? " 고급 옵션에서 로그인 경로를 입력해 주세요."
              : "")
          : "요청을 처리하지 못했습니다 (" +
            response.status +
            "). 입력과 서버 연결을 확인해 주세요.",
    );
  return data;
}
function Order({
  index,
  count,
  move,
}: {
  index: number;
  count: number;
  move: (delta: number) => void;
}) {
  return (
    <span className="order">
      {[-1, 1].map((d) => (
        <button
          type="button"
          key={d}
          aria-label={
            String(index + 1) + "번째 항목 " + (d < 0 ? "위로" : "아래로")
          }
          disabled={index + d < 0 || index + d >= count}
          onClick={() => move(d)}
        >
          {d < 0 ? "↑" : "↓"}
        </button>
      ))}
    </span>
  );
}
function moved<T>(list: T[], index: number, delta: number) {
  const next = [...list];
  [next[index], next[index + delta]] = [next[index + delta], next[index]];
  return next;
}
export default function Home() {
  const [page, setPage] = useState(0),
    [id, setId] = useState("");
  const [scenario, setScenario] = useState<Scenario | null>(null),
    [scene, setScene] = useState<SceneDoc | null>(null);
  const [stage, setStage] = useState(""),
    [error, setError] = useState(""),
    [warning, setWarning] = useState("");
  const [video, setVideo] = useState(""),
    [busy, setBusy] = useState(false),
    [arch, setArch] = useState(true);
  const [totalSec, setTotalSec] = useState(60);
  const [operation, setOperation] = useState<"build" | "scene">("build");
  const [poll, setPoll] = useState(0);
  const sample = page === 3 && !id;
  const path = "/" + encodeURIComponent(id);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "연결을 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (page !== 2) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const data = await request(path, "GET", undefined, controller.signal);
        if (controller.signal.aborted) return;
        setWarning(data.warning || "");
        setStage(data.stage);
        if (data.stage === "error") {
          setError(data.error || "영상 제작에 실패했습니다.");
          return;
        }
        if (data.stage === "done" && data.scene && data.videoUrl) {
          setScene(data.scene);
          setVideo(
            data.videoUrl +
              "?v=" +
              encodeURIComponent(data.updatedAt || Date.now()),
          );
          return;
        }
        timer = setTimeout(refresh, 1500);
      } catch {
        if (!controller.signal.aborted) {
          setStage("offline");
          setError("진행 상태를 가져올 수 없습니다.");
        }
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [page, path, poll]);
  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      fields = new FormData(form);
    const value = (key: string) => String(fields.get(key) || "");
    void act(async () => {
      const username = value("username"),
        password = value("password");
      if (Boolean(username) !== Boolean(password))
        throw new Error(
          "테스트 계정의 아이디와 비밀번호를 모두 입력해 주세요.",
        );
      const authPath = value("authPath").trim();
      if (authPath && username)
        throw new Error("테스트 계정과 로그인 경로 중 하나를 선택해 주세요.");
      const data = await request("", "POST", {
        repo: value("repo").trim(),
        url: value("url").trim(),
        totalSec: Number(value("seconds")),
        prompt: value("prompt").trim() || undefined,
        login: username ? { username, password } : undefined,
        auth: authPath
          ? {
              steps: [
                { id: 1, action: "goto", path: authPath, caption: "로그인" },
              ],
            }
          : undefined,
      });
      setTotalSec(Number(value("seconds")));
      setId(data.id);
      setScenario(data.scenario);
      setPage(1);
    });
  }
  async function produce(kind: "build" | "scene") {
    if (kind === "build") {
      await request(path + "/scenario", "PUT", scenario);
      await request(path + "/build", "POST", {
        includeArchitecture: arch,
        totalSec,
      });
    } else {
      await request(path + "/scene", "PUT", scene);
    }
    setOperation(kind);
    setWarning("");
    setVideo("");
    setStage("queued");
    setPage(2);
    setPoll((n) => n + 1);
  }
  function changeScenes(next: Scene[]) {
    if (scene)
      setScene({
        ...scene,
        scenes: next as SceneDoc["scenes"],
        totalSec: next.reduce((sum, s) => sum + s.durationSec, 0),
      });
  }
  function patchScene(i: number, next: Scene) {
    if (scene) changeScenes(scene.scenes.map((s, j) => (j === i ? next : s)));
  }
  return (
    <>
      <header>
        <strong>
          <i>▶</i> DemoDay
        </strong>
        <span>영상 스튜디오</span>
      </header>
      <main>
        <nav aria-label="제작 단계">
          {titles.map((t, i) => (
            <span key={t} aria-current={page === i ? "step" : undefined}>
              {t}
            </span>
          ))}
        </nav>
        <h1>{titles[page]}</h1>
        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        {page === 0 && (
          <form onSubmit={create}>
            <fieldset disabled={busy}>
              <label>
                GitHub 저장소 URL
                <input
                  required
                  type="url"
                  name="repo"
                  placeholder="https://github.com/team/project"
                />
              </label>
              <label>
                배포 URL
                <input
                  required
                  type="url"
                  name="url"
                  placeholder="https://project.example.com"
                />
              </label>
              <label>
                최대 발표 시간
                <select name="seconds">
                  {[60, 90, 180].map((n) => (
                    <option key={n} value={n}>
                      {n}초
                    </option>
                  ))}
                </select>
              </label>
              <details>
                <summary>테스트 계정 및 제작 요청 (선택)</summary>
                <label>
                  아이디
                  <input autoComplete="off" name="username" />
                </label>
                <label>
                  비밀번호
                  <input
                    type="password"
                    autoComplete="new-password"
                    name="password"
                  />
                </label>
                <label>
                  로그인 경로 (고급)
                  <input name="authPath" pattern="/.*" placeholder="/login" />
                </label>
                <label>
                  영상에 바라는 점
                  <textarea maxLength={500} name="prompt" rows={3} />
                </label>
              </details>
              <button className="primary">
                {busy ? "저장소 분석 중…" : "시나리오 확인 →"}
              </button>
              {process.env.NODE_ENV === "development" && (
                <button
                  type="button"
                  onClick={() => {
                    setScene(structuredClone(fixture) as SceneDoc);
                    setError("");
                    setPage(3);
                  }}
                >
                  샘플 장면 열기
                </button>
              )}
            </fieldset>
          </form>
        )}
        {page === 1 && scenario && (
          <fieldset disabled={busy}>
            <p>영상에 담을 단계를 순서대로 배치하세요.</p>
            {scenario.steps.map((s, i) => (
              <article key={s.id}>
                <b>
                  {i + 1}. {s.caption}
                </b>
                <div>
                  <Order
                    index={i}
                    count={scenario.steps.length}
                    move={(d) =>
                      setScenario({
                        ...scenario,
                        steps: moved(scenario.steps, i, d) as Scenario["steps"],
                      })
                    }
                  />
                  <button
                    disabled={scenario.steps.length === 1}
                    onClick={() =>
                      setScenario({
                        ...scenario,
                        steps: scenario.steps.filter(
                          (_, j) => j !== i,
                        ) as Scenario["steps"],
                      })
                    }
                  >
                    삭제
                  </button>
                </div>
              </article>
            ))}
            <label className="check">
              <input
                type="checkbox"
                checked={arch}
                onChange={(e) => setArch(e.target.checked)}
              />
              아키텍처 장면 포함
            </label>
            <button
              className="primary"
              onClick={() => act(() => produce("build"))}
            >
              {busy ? "요청 중…" : "영상 만들기"}
            </button>
          </fieldset>
        )}
        {page === 2 && (
          <section aria-live="polite">
            {warning && <p className="alert">{warning}</p>}
            {stage === "done" && video ? (
              <>
                <video controls src={video} />
                <a className="primary" href={video} download="DemoDay.mp4">
                  MP4 다운로드
                </a>
                <button onClick={() => setPage(3)}>장면 수정</button>
              </>
            ) : ["error", "offline"].includes(stage) ? (
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    if (stage === "offline") {
                      setStage("queued");
                      setPoll((n) => n + 1);
                    } else await produce(operation);
                  })
                }
              >
                다시 시도
              </button>
            ) : (
              <>
                <h2>{stages[stage] || "제작 상태 확인 중"}</h2>
                <progress />
                <p>영상 제작에는 보통 1~3분이 걸립니다.</p>
              </>
            )}
          </section>
        )}
        {page === 3 && scene && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => produce("scene"));
            }}
          >
            <fieldset disabled={busy}>
              {sample && (
                <p>
                  샘플 장면 편집{" "}
                  <button
                    type="button"
                    onClick={() =>
                      setScene(structuredClone(videoFixture) as SceneDoc)
                    }
                  >
                    녹화 샘플 불러오기
                  </button>
                </p>
              )}
              {scene.scenes.map((s, i) => (
                <section key={i}>
                  <article>
                    <b>
                      {i + 1}.{" "}
                      {
                        {
                          title: "제목",
                          screen: "화면 캡처",
                          architecture: "아키텍처",
                          points: "핵심 포인트",
                        }[s.type]
                      }
                    </b>
                    <Order
                      index={i}
                      count={scene.scenes.length}
                      move={(d) => changeScenes(moved(scene.scenes, i, d))}
                    />
                  </article>
                  {s.type === "screen" && !sample && (
                    <Image
                      unoptimized
                      src={"/api/runs" + path + "/files/" + s.image}
                      alt={"장면 " + (i + 1) + " 미리보기"}
                      width={160}
                      height={90}
                    />
                  )}
                  <label>
                    길이 (초)
                    <input
                      type="number"
                      min="0.01"
                      step="any"
                      required
                      value={s.durationSec || ""}
                      onChange={(e) =>
                        patchScene(i, {
                          ...s,
                          durationSec: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  {(s.type === "screen" || s.type === "title") && (
                    <label>
                      자막
                      <input
                        maxLength={160}
                        value={(s.type === "screen" ? s.caption : s.text) || ""}
                        onChange={(e) =>
                          patchScene(
                            i,
                            s.type === "screen"
                              ? { ...s, caption: e.target.value }
                              : { ...s, text: e.target.value },
                          )
                        }
                      />
                    </label>
                  )}
                </section>
              ))}
              {sample ? (
                <button type="button" onClick={() => setPage(0)}>
                  입력으로 돌아가기
                </button>
              ) : (
                <button className="primary">
                  {busy ? "저장 중…" : "저장하고 다시 렌더링"}
                </button>
              )}
            </fieldset>
          </form>
        )}
      </main>
    </>
  );
}
