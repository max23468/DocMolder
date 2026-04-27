from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import queue
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ZERO_SHA = "0" * 40


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw!r}") from exc


def normalize_repo_name(value: str) -> str:
    return value.strip().lower()


def normalize_branch(value: str) -> str:
    value = value.strip()
    if value.startswith("refs/heads/"):
        return value.removeprefix("refs/heads/")
    return value


def build_ref(branch: str) -> str:
    branch = normalize_branch(branch)
    return f"refs/heads/{branch}"


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret:
        return False
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


@dataclass(frozen=True)
class WebhookConfig:
    host: str
    port: int
    webhook_path: str
    health_path: str
    repository: str
    branch: str
    secret: str
    deploy_script: str
    deploy_timeout_seconds: int
    auto_release_script: str
    auto_release_timeout_seconds: int
    max_body_bytes: int

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        return cls(
            host=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_HOST", "127.0.0.1").strip(),
            port=env_int("DOCMOLDER_GITHUB_WEBHOOK_PORT", 8123),
            webhook_path=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_PATH", "/webhooks/github/deploy").strip() or "/webhooks/github/deploy",
            health_path=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_HEALTH_PATH", "/webhooks/github/healthz").strip() or "/webhooks/github/healthz",
            repository=normalize_repo_name(os.getenv("DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY", "max23468/DocMolder")),
            branch=normalize_branch(os.getenv("DOCMOLDER_GITHUB_WEBHOOK_BRANCH", "main")),
            secret=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_SECRET", "").strip(),
            deploy_script=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT", "/opt/docmolder/app/deploy/update-vps.sh").strip(),
            deploy_timeout_seconds=env_int("DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_TIMEOUT_SECONDS", 3600),
            auto_release_script=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_AUTO_RELEASE_SCRIPT", "/opt/docmolder/app/deploy/auto-release.sh").strip(),
            auto_release_timeout_seconds=env_int("DOCMOLDER_GITHUB_WEBHOOK_AUTO_RELEASE_TIMEOUT_SECONDS", 1200),
            max_body_bytes=env_int("DOCMOLDER_GITHUB_WEBHOOK_MAX_BODY_BYTES", 1_048_576),
        )

    @property
    def target_ref(self) -> str:
        return build_ref(self.branch)

    @property
    def ready(self) -> bool:
        return bool(self.secret) and Path(self.deploy_script).exists()


@dataclass
class DeployJob:
    delivery_id: str
    target_ref: str
    repository: str
    branch: str
    payload: dict[str, Any]
    received_at: str = field(default_factory=utc_now)


@dataclass
class DeployState:
    busy: bool = False
    last_job: dict[str, Any] | None = None
    last_result: dict[str, Any] | None = None
    last_error: str | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None


class GitHubDeployWebhookApp:
    def __init__(self, config: WebhookConfig) -> None:
        self.config = config
        self.jobs: queue.Queue[DeployJob] = queue.Queue()
        self.state = DeployState()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._worker_loop, name="docmolder-github-webhook-worker", daemon=True)

    def start(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.jobs.put(
            DeployJob(
                delivery_id="stop",
                target_ref=self.config.target_ref,
                repository=self.config.repository,
                branch=self.config.branch,
                payload={},
            )
        )
        self.worker.join(timeout=5)

    def enqueue(self, job: DeployJob) -> None:
        self.jobs.put(job)

    def status(self) -> dict[str, Any]:
        return {
            "ok": self.config.ready,
            "configured": self.config.ready,
            "busy": self.state.busy,
            "queued_jobs": self.jobs.qsize(),
            "webhook_path": self.config.webhook_path,
            "health_path": self.config.health_path,
            "repository": self.config.repository,
            "branch": self.config.branch,
            "auto_release_script": self.config.auto_release_script,
            "last_job": self.state.last_job,
            "last_result": self.state.last_result,
            "last_error": self.state.last_error,
            "last_started_at": self.state.last_started_at,
            "last_finished_at": self.state.last_finished_at,
        }

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue

            if job.delivery_id == "stop":
                self.jobs.task_done()
                break

            self.state.busy = True
            self.state.last_job = asdict(job)
            self.state.last_started_at = utc_now()
            self.state.last_error = None
            print(f"[webhook] deploy queued for {job.target_ref} ({job.delivery_id})", flush=True)

            try:
                self._run_deploy(job)
            except Exception as exc:  # pragma: no cover - defensive guard
                self.state.last_error = str(exc)
                if self.state.last_result is None or self.state.last_result.get("ok") is not False:
                    self.state.last_result = {
                        "ok": False,
                        "target_ref": job.target_ref,
                        "error": str(exc),
                        "finished_at": utc_now(),
                    }
                print(f"[webhook] deploy failed unexpectedly: {exc}", flush=True)
            finally:
                self.state.busy = False
                self.state.last_finished_at = utc_now()
                self.jobs.task_done()

    def _run_deploy(self, job: DeployJob) -> None:
        script = Path(self.config.deploy_script)
        if not script.exists():
            raise FileNotFoundError(f"Deploy script missing: {script}")

        command = [str(script), job.target_ref]
        print(f"[webhook] running: {' '.join(command)}", flush=True)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.config.deploy_timeout_seconds,
        )

        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"[deploy stdout] {line}", flush=True)
        if result.stderr:
            for line in result.stderr.splitlines():
                print(f"[deploy stderr] {line}", flush=True)

        self.state.last_result = {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "target_ref": job.target_ref,
            "delivery_id": job.delivery_id,
            "repository": job.repository,
            "branch": job.branch,
            "finished_at": utc_now(),
        }

        if result.returncode != 0:
            self.state.last_error = f"deploy exited with {result.returncode}"
            raise RuntimeError(f"Deploy script exited with {result.returncode}")

        print(f"[webhook] deploy OK for {job.target_ref}", flush=True)
        release_result = self._run_auto_release()
        self.state.last_result["auto_release"] = release_result
        self.state.last_result["ok"] = release_result["ok"]
        if not release_result["ok"]:
            self.state.last_error = f"auto release exited with {release_result['returncode']}"
            raise RuntimeError(self.state.last_error)

    def _run_auto_release(self) -> dict[str, Any]:
        script = Path(self.config.auto_release_script)
        if not script.exists():
            print(f"[webhook] auto release script missing: {script}; skipping", flush=True)
            return {"ok": True, "skipped": True, "reason": "script missing", "script": str(script), "returncode": 0}

        command = [str(script)]
        print(f"[webhook] running auto release: {' '.join(command)}", flush=True)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.config.auto_release_timeout_seconds,
        )
        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"[release stdout] {line}", flush=True)
        if result.stderr:
            for line in result.stderr.splitlines():
                print(f"[release stderr] {line}", flush=True)

        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "script": str(script),
            "finished_at": utc_now(),
        }


class GitHubDeployWebhookHandler(BaseHTTPRequestHandler):
    server: "GitHubDeployWebhookHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {self.server.app.config.health_path, "/status"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload = self.server.app.status()
        payload["path"] = self.path
        self._send_json(HTTPStatus.OK if payload["configured"] else HTTPStatus.SERVICE_UNAVAILABLE, payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != self.server.app.config.webhook_path:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not self.server.app.config.ready:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "webhook listener not configured"},
            )
            return

        event = self.headers.get("X-GitHub-Event", "")
        delivery_id = self.headers.get("X-GitHub-Delivery", "unknown")
        signature = self.headers.get("X-Hub-Signature-256")
        body = self._read_body()
        if body is None:
            return

        if not verify_signature(self.server.app.config.secret, body, signature):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "error": "invalid signature"},
            )
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json"})
            return

        if event == "ping":
            self._send_json(HTTPStatus.OK, {"ok": True, "event": "ping"})
            return

        if event != "push":
            self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "ignored": True, "reason": f"unsupported event: {event}"})
            return

        accept, target_ref, reason = should_accept_push(payload, self.server.app.config.repository, self.server.app.config.branch)
        if not accept:
            self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "ignored": True, "reason": reason})
            return

        job = DeployJob(
            delivery_id=delivery_id,
            target_ref=target_ref,
            repository=normalize_repo_name(str(payload["repository"]["full_name"])),
            branch=normalize_branch(str(payload["ref"])),
            payload=payload,
        )
        self.server.app.enqueue(job)
        self._send_json(
            HTTPStatus.ACCEPTED,
            {"ok": True, "queued": True, "delivery_id": delivery_id, "target_ref": target_ref},
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        print(f"[webhook] {self.address_string()} - {format % args}", flush=True)

    def _read_body(self) -> bytes | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"ok": False, "error": "missing content-length"})
            return None

        try:
            size = int(content_length)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid content-length"})
            return None

        if size > self.server.app.config.max_body_bytes:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "payload too large"})
            return None

        body = self.rfile.read(size)
        if len(body) != size:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "truncated request body"})
            return None
        return body

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GitHubDeployWebhookHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[BaseHTTPRequestHandler], app: GitHubDeployWebhookApp):
        super().__init__(server_address, RequestHandlerClass)
        self.app = app


def should_accept_push(payload: dict[str, Any], expected_repo: str, expected_branch: str) -> tuple[bool, str | None, str]:
    repository = normalize_repo_name(str(payload.get("repository", {}).get("full_name", "")))
    if repository != expected_repo:
        return False, None, f"repository mismatch: {repository!r}"

    ref = str(payload.get("ref", ""))
    if ref != build_ref(expected_branch):
        return False, None, f"ref mismatch: {ref!r}"

    if payload.get("deleted") is True:
        return False, None, "branch deleted"

    after = str(payload.get("after", ""))
    if not after or after == ZERO_SHA:
        return False, None, "missing target sha"

    return True, after, "push accepted"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DocMolder GitHub deploy webhook listener")
    parser.add_argument("--host", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=env_int("DOCMOLDER_GITHUB_WEBHOOK_PORT", 8123))
    parser.add_argument("--webhook-path", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_PATH", "/webhooks/github/deploy"))
    parser.add_argument("--health-path", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_HEALTH_PATH", "/webhooks/github/healthz"))
    parser.add_argument("--repository", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY", "max23468/DocMolder"))
    parser.add_argument("--branch", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_BRANCH", "main"))
    parser.add_argument("--secret", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_SECRET", ""))
    parser.add_argument("--deploy-script", default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT", "/opt/docmolder/app/deploy/update-vps.sh"))
    parser.add_argument(
        "--auto-release-script",
        default=os.getenv("DOCMOLDER_GITHUB_WEBHOOK_AUTO_RELEASE_SCRIPT", "/opt/docmolder/app/deploy/auto-release.sh"),
    )
    parser.add_argument(
        "--deploy-timeout-seconds",
        type=int,
        default=env_int("DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_TIMEOUT_SECONDS", 3600),
    )
    parser.add_argument(
        "--auto-release-timeout-seconds",
        type=int,
        default=env_int("DOCMOLDER_GITHUB_WEBHOOK_AUTO_RELEASE_TIMEOUT_SECONDS", 1200),
    )
    parser.add_argument(
        "--max-body-bytes",
        type=int,
        default=env_int("DOCMOLDER_GITHUB_WEBHOOK_MAX_BODY_BYTES", 1_048_576),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = WebhookConfig(
        host=args.host,
        port=args.port,
        webhook_path=args.webhook_path,
        health_path=args.health_path,
        repository=normalize_repo_name(args.repository),
        branch=normalize_branch(args.branch),
        secret=args.secret.strip(),
        deploy_script=args.deploy_script,
        deploy_timeout_seconds=args.deploy_timeout_seconds,
        auto_release_script=args.auto_release_script,
        auto_release_timeout_seconds=args.auto_release_timeout_seconds,
        max_body_bytes=args.max_body_bytes,
    )
    app = GitHubDeployWebhookApp(config)
    server = GitHubDeployWebhookHTTPServer((config.host, config.port), GitHubDeployWebhookHandler, app)

    print(
        json.dumps(
            {
                "ok": True,
                "host": config.host,
                "port": config.port,
                "webhook_path": config.webhook_path,
                "health_path": config.health_path,
                "repository": config.repository,
                "branch": config.branch,
                "auto_release_script": config.auto_release_script,
                "configured": config.ready,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    app.start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        app.stop()


if __name__ == "__main__":
    main()
