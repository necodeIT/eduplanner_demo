from __future__ import annotations

import json
import os
import socketserver
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .adapter_moodlecli import MoodleCLI
from .config import Config
from .logger import Logger
from .populate import StateStore, apply, config_hash


MAX_REQUEST = 4 * 1024 * 1024


def wait_for_stable_hash(
    config: Config,
    quiet_seconds: float = 0.5,
    poll_seconds: float = 0.1,
    *,
    reader: Callable[[Config], str] = config_hash,
    clock: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> str:
    """Return only after the two-file content hash has stopped changing."""
    candidate: str | None = None
    stable_since = clock()
    while True:
        try:
            current = reader(config)
        except Exception as error:
            current = f"invalid:{error}"
        now = clock()
        if current != candidate:
            candidate = current
            stable_since = now
        elif now - stable_since >= quiet_seconds:
            return current
        pause(poll_seconds)


class AgentContext:
    def __init__(
        self,
        config: Config,
        schema_dir: Path,
        state: StateStore,
        request_apply: Callable[[], None],
    ):
        self.config = config
        self.schema_dir = schema_dir
        self.state = state
        self.request_apply = request_apply

    def status(self) -> dict[str, Any]:
        result = self.state.read()
        result["watcher"] = {"running": True, "pid": os.getpid()}
        result["lastApply"] = result.get("updatedAt")
        result["appliedHash"] = result.get("hash")
        try:
            result["currentHash"] = config_hash(self.config)
        except Exception as error:
            result["currentHashError"] = str(error)
        return result

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("operation")
        if operation == "read":
            courses, users = self.config.raw()
            return {"courses": courses, "users": users, "status": self.status()}
        if operation == "status":
            return self.status()
        if operation == "validate":
            parsed = self.config.from_data(request.get("courses"), request.get("users"))
            return {
                "valid": True,
                "counts": {
                    "courses": len(parsed.courses),
                    "activities": len(parsed.activities),
                    "users": len(parsed.users),
                },
            }
        if operation == "save":
            with self.state.lock():
                self.config.save(request.get("courses"), request.get("users"))
                saved_hash = config_hash(self.config)
            self.request_apply()
            return {"saved": True, "hash": saved_hash}
        if operation == "apply":
            self.request_apply()
            return {"queued": True}
        raise ValueError(f"Unsupported agent operation: {operation!r}")


class AgentHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            response = {"ok": False, "error": "Request is too large"}
        else:
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("Request must be a JSON object")
                result = self.server.context.dispatch(request)  # type: ignore[attr-defined]
                response = {"ok": True, "result": result}
            except Exception as error:
                response = {"ok": False, "error": str(error)}
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode() + b"\n")


class AgentServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, context: AgentContext):
        self.context = context
        super().__init__(path, AgentHandler)


def watch(config: Config, adapter: MoodleCLI, schema_dir: Path, state: StateStore) -> None:
    socket_path = Path(os.getenv("DEMO_AGENT_SOCKET", "/run/eduplanner-demo/agent.sock"))
    try:
        socket_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        socket_path = state.directory / "agent.sock"
    socket_path.unlink(missing_ok=True)
    requested = threading.Event()
    requested.set()
    context = AgentContext(config, schema_dir, state, requested.set)
    server = AgentServer(str(socket_path), context)
    os.chmod(socket_path, 0o660)
    if os.geteuid() == 0:
        _, group, _ = adapter.runtime_account()
        os.chown(socket_path, 0, group)
    server_thread = threading.Thread(target=server.serve_forever, name="demo-agent", daemon=True)
    server_thread.start()
    Logger.info(f"Watching configuration; editor agent listening on {socket_path}")
    last_observed = ""
    try:
        while True:
            try:
                observed = config_hash(config)
            except Exception as error:
                observed = f"invalid:{error}"
                if observed != last_observed:
                    state.write({"state": "failed", "error": str(error)})
                    Logger.error(error)
            if observed != last_observed and not observed.startswith("invalid:"):
                requested.set()
            last_observed = observed
            if requested.wait(timeout=0.75):
                requested.clear()
                stable = wait_for_stable_hash(config)
                last_observed = stable
                if stable.startswith("invalid:"):
                    error = stable.removeprefix("invalid:")
                    state.write({"state": "failed", "error": error})
                    Logger.error(error)
                else:
                    try:
                        apply(config, adapter, schema_dir, state)
                    except Exception as error:
                        Logger.error(error)
            time.sleep(0.25)
    finally:
        server.shutdown()
        server.server_close()
        socket_path.unlink(missing_ok=True)
