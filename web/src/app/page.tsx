"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import type { FormEvent } from "react";
import Image from "next/image";
import type { Scenario, SceneDoc } from "@demoday/contracts";
import Editor from "./editor";
import presets from "../../../backend/samples.json";

import videoFixture from "@demoday/contracts/fixtures/scene.video.json";
import fixture from "@demoday/contracts/fixtures/scene.json";

const titles = ["프로젝트 입력", "시나리오 확인", "영상 미리보기", "장면 수정"];
const stages: Record<string, string> = {
  queued: "제작 대기 중",
  capturing: "웹 화면 캡처 중",
  scening: "장면 구성 중",
  rendering: "영상 렌더링 중",
};
const recoveryKey = "demoday.activeRun";
type Operation = "build" | "scene";
function rememberRun(id: string, operation: Operation = "build") {
  try {
    if (id)
      sessionStorage.setItem(recoveryKey, JSON.stringify({ id, operation }));
    else sessionStorage.removeItem(recoveryKey);
  } catch {
    /* The current run still works when browser storage is unavailable. */
  }
}
function recalledRun(): { id: string; operation: Operation } | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(recoveryKey) || "null");
    if (
      typeof saved?.id === "string" &&
      saved.id &&
      ["build", "scene"].includes(saved.operation)
    )
      return saved;
  } catch {
    /* Ignore unavailable storage or an invalid saved entry. */
  }
  return null;
}
class RunRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}
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
    throw new RunRequestError(
      response.status,
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
const subscribe = () => () => {};
export default function Home() {
  const hydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  return hydrated ? (
    <Studio />
  ) : (
    <main aria-busy="true">프로젝트 확인 중…</main>
  );
}
function Studio() {
  const [initialRun] = useState(recalledRun);
  const [page, setPage] = useState(initialRun ? 2 : 0),
    [id, setId] = useState(initialRun?.id || "");
  const [scenario, setScenario] = useState<Scenario | null>(null),
    [scene, setScene] = useState<SceneDoc | null>(null);
  const [stage, setStage] = useState(""),
    [error, setError] = useState(""),
    [warning, setWarning] = useState("");
  const [video, setVideo] = useState(""),
    [busy, setBusy] = useState(false);
  const [repo, setRepo] = useState(""),
    [url, setUrl] = useState(""),
    [prompt, setPrompt] = useState("");
  const [totalSec, setTotalSec] = useState(60);
  const [operation, setOperation] = useState<Operation>(
    initialRun?.operation || "build",
  );
  const [duration, setDuration] = useState(0);
  const [poll, setPoll] = useState(0);
  const sample = page === 3 && !id;
  const path = "/" + encodeURIComponent(id);
  const posterImage = scene?.scenes.find(
    (item) => item.type === "screen",
  )?.image;
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
        setRepo(data.repo || "");
        setUrl(data.url || "");
        setTotalSec(data.totalSec || 60);
        if (data.scenario) setScenario(data.scenario);
        if (data.scene) setScene(data.scene);
        if (data.stage === "analyzed" && data.scenario) {
          setPage(1);
          return;
        }
        setWarning(data.warning || "");
        setStage(data.stage);
        if (data.stage === "error") {
          setError(data.error || "영상 제작에 실패했습니다.");
          return;
        }
        if (data.stage === "done") {
          if (!data.scene || !data.videoUrl) {
            setStage("offline");
            setError("제작은 끝났지만 결과 파일을 불러올 수 없습니다.");
            return;
          }
          setVideo(
            data.videoUrl +
              "?v=" +
              encodeURIComponent(data.updatedAt || Date.now()),
          );
          return;
        }
        timer = setTimeout(refresh, 1500);
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof RunRequestError && error.status === 404) {
          rememberRun("");
          setId("");
          setPage(0);
          setError(
            "이전 작업을 찾을 수 없습니다. 새 프로젝트를 시작해 주세요.",
          );
        } else {
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
      rememberRun(data.id);
      setId(data.id);
      setScenario(data.scenario);
      setPage(1);
    });
  }
  async function produce(kind: "build" | "scene", edited = scene) {
    if (kind === "build") {
      await request(path + "/scenario", "PUT", scenario);
      await request(path + "/build", "POST", {
        totalSec,
      });
    } else {
      await request(path + "/scene", "PUT", edited);
    }
    rememberRun(id, kind);
    if (edited) setScene(edited);
    setOperation(kind);
    setWarning("");
    setDuration(0);
    setVideo("");
    setStage("queued");
    setPage(2);
    setPoll((n) => n + 1);
  }
  return (
    <>
      <header>
        <strong>
          <span className="brand-mark">
            <Image
              src="/demoday-logo.webp"
              alt=""
              width={96}
              height={96}
              priority
            />
          </span>
          DemoDay
        </strong>
        <span className="studio-name">영상 스튜디오</span>
      </header>
      <main className={page === 3 ? "wide" : page === 0 ? "intake" : ""}>
        <aside className="workflow">
          <h2>제작 과정</h2>
          <nav aria-label="제작 단계">
            {titles.map((t, i) => (
              <span
                key={t}
                aria-current={page === i ? "step" : undefined}
                data-complete={i < page}
              >
                <em aria-hidden="true">{i < page ? "✓" : i + 1}</em> {t}
              </span>
            ))}
          </nav>
        </aside>
        <div className="workspace">
          <h1>
            {
              [
                "어떤 프로젝트를 시연할까요?",
                "이 순서로 촬영할까요?",
                stage === "done" ? "영상이 완성됐어요" : "영상 미리보기",
                "장면 수정",
              ][page]
            }
          </h1>
          <p className="intro">
            {
              [
                "저장소와 배포 주소를 입력하면 실제 서비스 화면으로 발표 영상을 만듭니다.",
                "필요한 장면만 남기고 촬영할 순서를 정하세요.",
                stage === "done"
                  ? "완성된 영상을 내려받거나 장면별 자막을 다듬으세요."
                  : "이 화면에서 제작 진행 상황을 확인할 수 있어요.",
                "장면을 선택해 순서, 길이와 자막을 조정하세요.",
              ][page]
            }
          </p>
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
          {page === 0 && (
            <form onSubmit={create}>
              <fieldset disabled={busy}>
                <h2>프로젝트 정보</h2>
                <div className="presets">
                  <small>예시로 채우기</small>
                  {presets.map((p) => (
                    <button
                      key={p.repo}
                      type="button"
                      onClick={() => {
                        setRepo(p.repo);
                        setUrl(p.url);
                        setPrompt(p.prompt || "");
                        setError("");
                      }}
                    >
                      {p.repo.replace("https://github.com/", "")} 예시
                    </button>
                  ))}
                </div>
                <div className="project-urls">
                  <label>
                    GitHub 저장소 URL
                    <input
                      required
                      type="url"
                      name="repo"
                      value={repo}
                      onChange={(e) => setRepo(e.target.value)}
                      placeholder="https://github.com/team/project"
                    />
                    <small>
                      저장소를 분석해 시연할 화면과 기능을 찾습니다.
                    </small>
                  </label>
                  <label>
                    배포 URL
                    <input
                      required
                      type="url"
                      name="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://project.example.com"
                    />
                    <small>이 주소에서 실제 서비스 화면을 촬영합니다.</small>
                  </label>
                </div>
                <fieldset className="length">
                  <legend>최대 영상 길이</legend>
                  {[60, 90, 180].map((n) => (
                    <label key={n}>
                      <input
                        type="radio"
                        name="seconds"
                        value={n}
                        checked={totalSec === n}
                        onChange={() => setTotalSec(n)}
                      />
                      {n}초
                    </label>
                  ))}
                  <small>실제 영상은 내용에 따라 더 짧아질 수 있어요.</small>
                </fieldset>
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
                    <textarea
                      maxLength={500}
                      name="prompt"
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      rows={3}
                    />
                  </label>
                </details>
                <button className="primary">
                  {busy ? "저장소 분석 중…" : "시나리오 확인 →"}
                </button>
                {process.env.NODE_ENV === "development" && (
                  <button
                    type="button"
                    onClick={() => {
                      setId("");
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
              <div className="meta">
                {repo.replace("https://github.com/", "")} · 최대 {totalSec}초
              </div>
              <h2>촬영 순서</h2>
              {scenario.steps.map((s, i) => (
                <article key={s.id}>
                  <b>
                    {i + 1}. {s.caption}
                    <small>{s.path}</small>
                  </b>
                  <div>
                    <Order
                      index={i}
                      count={scenario.steps.length}
                      move={(d) =>
                        setScenario({
                          ...scenario,
                          steps: moved(
                            scenario.steps,
                            i,
                            d,
                          ) as Scenario["steps"],
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

              <button
                className="primary"
                onClick={() => act(() => produce("build"))}
              >
                {busy ? "요청 중…" : "영상 만들기"}
              </button>
              <button onClick={() => setPage(0)}>프로젝트 정보 수정</button>
              <small>제작에는 보통 1~3분이 걸립니다.</small>
            </fieldset>
          )}
          {page === 2 && (
            <section aria-live="polite">
              {warning && <p className="alert">{warning}</p>}
              {stage === "done" && video ? (
                <>
                  <h2>{repo.replace("https://github.com/", "")}</h2>
                  <small>
                    프로젝트 데모 영상
                    {duration > 0 &&
                      " · " +
                        Math.floor(duration / 60) +
                        ":" +
                        String(Math.floor(duration % 60)).padStart(2, "0")}
                  </small>
                  <video
                    controls
                    poster={
                      posterImage
                        ? "/api/runs" + path + "/files/" + posterImage
                        : undefined
                    }
                    src={video}
                    onLoadedMetadata={(e) =>
                      setDuration(e.currentTarget.duration)
                    }
                  />
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
                  <ol className="progress">
                    {Object.entries(stages).map(([key, label]) => (
                      <li
                        key={key}
                        aria-current={key === stage ? "step" : undefined}
                      >
                        {label}
                      </li>
                    ))}
                  </ol>
                  <progress aria-label="영상 제작 중" />
                  <p>영상 제작에는 보통 1~3분이 걸립니다.</p>
                </>
              )}
              <div className="restart-row">
                {" "}
                <button
                  className="restart"
                  onClick={() => {
                    rememberRun("");
                    window.location.reload();
                  }}
                >
                  새 프로젝트 시작
                </button>
              </div>
            </section>
          )}
          {sample && (
            <button
              onClick={() =>
                setScene(structuredClone(videoFixture) as SceneDoc)
              }
            >
              녹화 샘플 불러오기
            </button>
          )}
          {page === 3 && scene && (
            <Editor
              key={sample ? JSON.stringify(scene) : id}
              initial={scene}
              busy={busy}
              files={sample ? "" : "/api/runs" + path + "/files/"}
              back={() => setPage(sample ? 0 : 2)}
              save={(doc) => act(() => produce("scene", doc))}
            />
          )}
        </div>
      </main>
    </>
  );
}
