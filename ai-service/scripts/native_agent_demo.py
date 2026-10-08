"""Native, synthetic-only Agent demo using an existing Memos binary and this venv."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTION = "DevMemo AI 的项目目标和技术边界是什么？"
SYNTHETIC_MEMOS = (
    "# DevMemo AI 演示目标\n仅用于简历的合成记录。Memos 保存原始记录和权限，FastAPI 提供派生 AI 服务。",
    "# DevMemo AI Agent\n合成技术记录：认证同源 BFF 查询可见 Memo，返回服务端引用；project_summary 生成 Markdown 报告。",
)


class DemoError(RuntimeError):
    """A concise diagnostic that never includes credentials or response bodies."""


def demo_environment(run_dir: Path, ai_port: int, inherited: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if inherited is None else inherited
    prefixes = ("AI_", "MEMOS_", "OPENAI_", "DEEPSEEK_", "OLLAMA_", "QDRANT_")
    excluded = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "PYTHONHOME", "PYTHONPATH"}
    environment = {
        key: value for key, value in source.items()
        if not key.upper().startswith(prefixes) and key.upper() not in excluded
    }
    environment.update({
        "AI_PROVIDER": "deterministic",
        "AI_EMBEDDING_PROVIDER": "deterministic",
        "AI_VECTOR_STORE": "memory",
        "AI_INDEX_MODE": "memo",
        "AI_INDEX_ON_WEBHOOK": "true",
        "AI_PUBLIC_CHUNK_RETRIEVAL": "false",
        "AI_AGENT_ENABLED": "true",
        "AI_AGENT_INTERNAL_URL": f"http://127.0.0.1:{ai_port}",
        "AI_AGENT_INTERNAL_SECRET": secrets.token_urlsafe(32),
        "AI_AGENT_PROVIDER_MASTER_KEY": secrets.token_urlsafe(32),
        "AI_AGENT_REHYDRATION_ENABLED": "false",
        "AI_AGENT_LIFECYCLE_ENABLED": "false",
        "AI_NOTES_DB": str(run_dir / "ai-notes.db"),
        "PYTHONPATH": str(REPO_ROOT / "ai-service"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GOMAXPROCS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    return environment


def resolve_memos_exe(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise DemoError("Memos portable executable not found; pass --memos-exe. No build is performed.")
    if resolved.name.lower().endswith(("-setup.exe", "_setup.exe")):
        raise DemoError("Use the portable Memos executable, not a Setup installer.")
    return resolved


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalAPI:
    def __init__(self, origin: str):
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise DemoError("Demo requests require an HTTP loopback origin with an explicit port.")
        self.origin = origin
        self.token = ""
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def request(self, method: str, path: str, body: dict[str, Any] | None = None,
                *, expected: int = 200, timeout: float = 30) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise DemoError("Invalid local API path.")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        encoded = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(self.origin + path, data=encoded, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        except (URLError, TimeoutError, OSError) as error:
            cause = error.reason if isinstance(error, URLError) else error
            raise DemoError(f"{method} {path}: local service unavailable ({type(cause).__name__})") from error
        if status != expected:
            raise DemoError(f"{method} {path}: expected HTTP {expected}, received {status}")
        try:
            result = json.loads(raw) if raw else {}
        except ValueError as error:
            raise DemoError(f"{method} {path}: invalid JSON response") from error
        if not isinstance(result, dict):
            raise DemoError(f"{method} {path}: invalid response shape")
        return result


def save_artifact(run_dir: Path, filename: str, artifact: dict[str, Any]) -> Path:
    markdown = artifact.get("markdown")
    if artifact.get("media_type") != "text/markdown" or not isinstance(markdown, str) or not markdown.strip():
        raise DemoError("AgentRun did not return a Markdown artifact.")
    encoded = markdown.encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != artifact.get("digest"):
        raise DemoError("AgentRun artifact digest mismatch.")
    target = run_dir / filename
    if target.parent != run_dir:
        raise DemoError("Invalid report filename.")
    target.write_bytes(encoded)
    return target


def available_port(requested: int) -> int:
    if not 0 <= requested <= 65535:
        raise DemoError("Port must be between 0 and 65535.")
    try:
        with socket.socket() as connection:
            connection.bind(("127.0.0.1", requested))
            return int(connection.getsockname()[1])
    except OSError as error:
        raise DemoError(f"Loopback port {requested} is occupied; existing services are preserved.") from error


class ChildService:
    def __init__(self, command: list[str], environment: dict[str, str], cwd: Path, log_path: Path):
        self.log = log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                command, cwd=cwd, env=environment, stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except BaseException:
            self.log.close()
            raise

    def wait_ready(self, api: LocalAPI, path: str) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise DemoError("Demo child exited before readiness; inspect its local log.")
            try:
                api.request("GET", path, timeout=1)
                return
            except DemoError:
                time.sleep(0.25)
        raise DemoError("Demo child did not become ready within 30 seconds.")

    def stop(self) -> None:
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.log.close()


def sign_in(api: LocalAPI, username: str, password: str) -> dict[str, Any]:
    response = api.request("POST", "/api/v1/auth/signin", {
        "passwordCredentials": {"username": username, "password": password},
    })
    api.token = response["accessToken"]
    return response["user"]


def deterministic_setting() -> dict[str, Any]:
    return {"version": "agent-provider-config-v1", "provider": "deterministic", "model": "", "base_url": "",
            "enabled": True, "allow_real_memo_data": False}


def verify_demo(api: LocalAPI, ai_origin: str, run_dir: Path, checks: list[str]) -> tuple[str, str]:

    def check(name: str, passed: bool) -> None:
        if not passed:
            raise DemoError(f"Demo check failed: {name}")
        checks.append(name)

    password = "Synthetic-" + secrets.token_urlsafe(12)
    api.request("POST", "/api/v1/users", {"username": "demo", "password": password, "role": "ADMIN"})
    user = sign_in(api, "demo", password)
    check("synthetic_admin_login", user["role"] == "ADMIN")
    anonymous = LocalAPI(api.origin)
    anonymous.request("POST", "/api/ai/agent/answer", expected=401)
    checks.append("anonymous_agent_rejected")
    setting = api.request("PUT", "/api/ai/agent/provider", deterministic_setting())
    check("deterministic_setting_saved", setting["provider"] == "deterministic" and not setting["api_key_set"])
    read = api.request("GET", "/api/ai/agent/provider")
    check("masked_setting_read", "api_key" not in read and read["config_version"] == setting["config_version"])
    connection = api.request("POST", "/api/ai/agent/provider/test")
    check("synthetic_connection_test", connection["status"] == "ok" and connection["provider"] == "deterministic")
    api.request("POST", f"/api/v1/{user['name']}/webhooks", {
        "url": ai_origin + "/api/integrations/memos/webhook", "displayName": "Synthetic native demo",
    })
    memo_uids = []
    for content in SYNTHETIC_MEMOS:
        memo = api.request("POST", "/api/v1/memos", {"content": content, "visibility": "PRIVATE"})
        memo_uids.append(memo["name"].split("/")[-1])
    deadline = time.monotonic() + 15
    answer = {}
    while time.monotonic() < deadline:
        answer = api.request("POST", "/api/ai/agent/answer", {"question": QUESTION, "limit": 5})
        citations = answer.get("citations", [])
        if {item["memo_id"] for item in citations} == set(memo_uids):
            break
        time.sleep(0.25)
    check("memos_webhook_to_citations", {item["memo_id"] for item in answer.get("citations", [])} == set(memo_uids))
    check("grounded_answer", answer["trace"]["terminal_state"] == "answered" and bool(answer["answer"]))
    (run_dir / "evidence-answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")

    reader = LocalAPI(api.origin)
    api.request("POST", "/api/v1/users", {"username": "reader", "password": password, "role": "USER"})
    sign_in(reader, "reader", password)
    reader.request("GET", "/api/ai/agent/provider", expected=403)
    checks.append("non_admin_setting_rejected")
    empty = reader.request("POST", "/api/ai/agent/answer", {"question": QUESTION, "limit": 5})
    check("private_memos_excluded", empty["citations"] == [] and empty["trace"]["terminal_state"] == "no_context")
    reader.request("POST", "/api/ai/agent/runs", {
        "task_kind": "project_summary", "request_key": "forbidden-source", "memo_uids": memo_uids,
    }, expected=400)
    checks.append("invisible_run_source_rejected")

    def report(request_key: str, filename: str) -> dict[str, Any]:
        run = api.request("POST", "/api/ai/agent/runs", {
            "task_kind": "project_summary", "request_key": request_key, "memo_uids": memo_uids,
        })
        check(request_key + "_succeeded", run["status"] == "succeeded" and run["source_count"] == len(memo_uids))
        status = api.request("GET", f"/api/ai/agent/runs/{run['run_id']}")
        check(request_key + "_status", status["artifact_id"] == run["artifact_id"] and status["status"] == "succeeded")
        artifact = api.request("GET", f"/api/ai/agent/runs/{run['run_id']}/artifact")
        save_artifact(run_dir, filename, artifact)
        checks.append(request_key + "_download_digest")
        replay = api.request("POST", "/api/ai/agent/runs", {
            "task_kind": "project_summary", "request_key": request_key, "memo_uids": memo_uids,
        })
        check(request_key + "_idempotent_replay", replay["run_id"] == run["run_id"]
              and replay["artifact_id"] == run["artifact_id"] and replay["status"] == "succeeded")
        reader.request("GET", f"/api/ai/agent/runs/{run['run_id']}/artifact", expected=404)
        checks.append(request_key + "_creator_only")
        return artifact

    normal = report("native-deterministic", "project-summary.md")
    check("normal_report_has_no_fallback", "deterministic fallback" not in normal["markdown"])
    # The existing consent guard rejects this configuration BEFORE constructing/calling Ollama.
    # This is a configuration-failure demonstration; it is not real-Provider acceptance.
    api.request("PUT", "/api/ai/agent/provider", {
        "version": "agent-provider-config-v1", "provider": "ollama", "model": "synthetic-demo",
        "base_url": "http://127.0.0.1:11434", "enabled": True, "allow_real_memo_data": False,
    })
    try:
        fallback = report("native-config-fallback", "project-summary-fallback.md")
        check("fallback_explicitly_marked", "deterministic fallback" in fallback["markdown"])
    finally:
        api.request("PUT", "/api/ai/agent/provider", deterministic_setting())
    check("deterministic_restored", api.request("GET", "/api/ai/agent/provider")["provider"] == "deterministic")
    return password, memo_uids[0]


def run_demo(executable: Path, memos_port: int, ai_port: int, verify_only: bool) -> None:
    executable = resolve_memos_exe(executable)
    memos_port, ai_port = available_port(memos_port), available_port(ai_port)
    if memos_port == ai_port:
        raise DemoError("Memos and AI Service require distinct ports.")
    runtime_root = REPO_ROOT / ".devmemo-local" / "runtime"
    if not runtime_root.resolve().is_relative_to(REPO_ROOT):
        raise DemoError("Demo runtime directory must stay inside the project.")
    runtime_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="native-agent-demo-", dir=runtime_root))
    memos_data = run_dir / "memos"
    memos_data.mkdir()
    environment = demo_environment(run_dir, ai_port)
    api, ai_api = LocalAPI(f"http://127.0.0.1:{memos_port}"), LocalAPI(f"http://127.0.0.1:{ai_port}")
    children: list[ChildService] = []
    with executable.open("rb") as binary:
        binary_digest = hashlib.file_digest(binary, "sha256").hexdigest()
    summary: dict[str, Any] = {
        "mode": "synthetic-native-http", "memos_binary_sha256": binary_digest,
        "service_ports": {"memos": memos_port, "ai": ai_port}, "process_ids": [],
        "ui_verified": False, "real_provider_called": False, "checks": [], "passed": False,
    }
    print(f"Synthetic demo data and reports: {run_dir}", flush=True)
    try:
        ai = ChildService([
            sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(ai_port),
            "--workers", "1",
        ], environment, REPO_ROOT / "ai-service", run_dir / "ai-service.log")
        children.append(ai)
        summary["process_ids"].append(ai.process.pid)
        ai.wait_ready(ai_api, "/health")
        memos = ChildService([
            str(executable), "--addr", "127.0.0.1", "--port", str(memos_port), "--data", str(memos_data),
            "--driver", "sqlite", "--allow-private-webhooks",
        ], environment, REPO_ROOT, run_dir / "memos.log")
        children.append(memos)
        summary["process_ids"].append(memos.process.pid)
        memos.wait_ready(api, "/api/v1/instance/profile")
        checks = summary["checks"]
        password, first_uid = verify_demo(api, ai_api.origin, run_dir, checks)
        if verify_only:
            ai.stop()
            api.request("POST", "/api/ai/agent/answer", {"question": QUESTION, "limit": 5}, expected=503)
            checks.append("missing_ai_reports_503")
            memo = api.request("GET", f"/api/v1/memos/{first_uid}")
            if not memo.get("content"):
                raise DemoError("Core Memo read failed after AI Service stopped.")
            checks.append("core_memo_survives_ai_stop")
        summary.update(checks=checks, passed=True)
        (run_dir / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"DEVMEMO_NATIVE_DEMO_OK: {len(checks)} HTTP checks", flush=True)
        if not verify_only:
            print(f"Demo URL: {api.origin}\nSynthetic login: demo\nSynthetic password: {password}", flush=True)
            print("Reports are ready. Ctrl+C stops only this demo's two processes. No browser is opened.", flush=True)
            while True:
                if any(child.process.poll() is not None for child in children):
                    raise DemoError("A demo service exited; inspect the local logs.")
                time.sleep(1)
    finally:
        for child in reversed(children):
            child.stop()
        summary["processes_stopped"] = all(child.process.poll() is not None for child in children)
        (run_dir / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memos-exe", type=Path, required=True, help="Existing portable binary; never a Setup installer")
    parser.add_argument("--memos-port", type=int, default=0, help="0 chooses a free loopback port")
    parser.add_argument("--ai-port", type=int, default=0, help="0 chooses a free loopback port")
    parser.add_argument("--verify-only", action="store_true", help="Verify HTTP success/failure paths, then stop both services")
    args = parser.parse_args()
    try:
        run_demo(args.memos_exe, args.memos_port, args.ai_port, args.verify_only)
    except KeyboardInterrupt:
        return 0
    except (DemoError, OSError, KeyError, ValueError) as error:
        print(f"Native demo failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
