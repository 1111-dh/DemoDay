"""Run the real UI and pipeline on private loopback ports; preserve evidence in runs/."""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from captions import verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def server(command, cwd, env, log, ready):
    with log.open("w") as stream:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        )
        try:
            deadline = time.monotonic() + 120
            while proc.poll() is None and time.monotonic() < deadline:
                try:
                    with urlopen(ready, timeout=4):
                        break
                except (URLError, TimeoutError):
                    time.sleep(0.4)
            else:
                raise RuntimeError(f"Server failed to start: {log}")
            yield
        finally:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True
                    )
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=20)


def main():
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="video-regression-", dir=runs))
    print(f"Video regression evidence: {out}", flush=True)
    env = dict(
        os.environ,
        PYTHONUTF8="1",
        VIDEO_TEST_OUTPUT=str(out),
        BAZE_API_KEY="",
        GROQ_API_KEY="",
        ANTHROPIC_API_KEY="",
        CAPTURE_MODE="script",
        NEXT_TELEMETRY_DISABLED="1",
        PYTHONPATH=str(ROOT / "backend"),
    )
    with ExitStack() as stack:
        api_port = port()
        api = f"http://127.0.0.1:{api_port}"
        stack.enter_context(
            server(
                [sys.executable, "-m", "uvicorn", "fixture_api:app", "--port", str(api_port)],
                HERE,
                env,
                out / "api.log",
                api,
            )
        )
        # Isolate Next's cache, dev lock and generated types.
        web = ROOT / "web"
        temp = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix=".video-test-", dir=ROOT))
        )
        for item in ["package.json", "tsconfig.json", "next.config.ts", "src", "public"]:
            source = web / item
            if source.is_dir():
                shutil.copytree(source, temp / item)
            else:
                shutil.copy(source, temp / item)
        modules = web / "node_modules"
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(temp / "node_modules"), str(modules)], check=True
            )
        else:
            (temp / "node_modules").symlink_to(modules, target_is_directory=True)
        web_port = port()
        ui = f"http://127.0.0.1:{web_port}"
        stack.enter_context(
            server(
                [
                    "node",
                    str(modules / "next/dist/bin/next"),
                    "dev",
                    "-H",
                    "127.0.0.1",
                    "-p",
                    str(web_port),
                ],
                temp,
                dict(env, DEMODAY_API_URL=api),
                out / "web.log",
                ui,
            )
        )
        subprocess.run(["node", str(HERE / "flow.cjs"), ui, api, str(out)], cwd=ROOT, check=True)
        verify(out)


if __name__ == "__main__":
    main()
