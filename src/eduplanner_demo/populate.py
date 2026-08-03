from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode, urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen

from . import __version__
from .adapter_moodlecli import MoodleCLI
from .config import Config, ConfigError
from .logger import Logger
from .model import DemoConfig
from .schemagen import generate_schemas


POPULATOR_VERSION = "4"
INTEGRATION_MANIFEST = "integration-manifest.json"


def base_url() -> str:
    value = os.getenv("DEMO_BASE_URL", "")
    parsed = urlparse(value)
    try:
        parsed.port
    except ValueError as error:
        raise ConfigError("DEMO_BASE_URL contains an invalid port") from error
    loopback_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        parsed.scheme != "https" and not loopback_http
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "DEMO_BASE_URL must be an HTTPS origin, or an HTTP loopback origin for local testing, "
            "without a path, query, or fragment"
        )
    return value


class StateStore:
    def __init__(self, directory: str | Path | None = None):
        fallback = Path.cwd() / ".demo-state"
        requested = Path(directory or os.getenv("DEMO_STATE_DIR", "/var/lib/eduplanner-demo"))
        try:
            requested.mkdir(parents=True, exist_ok=True)
            self.directory = requested
        except OSError:
            fallback.mkdir(parents=True, exist_ok=True)
            self.directory = fallback
        self.path = self.directory / "status.json"
        self.lock_path = self.directory / "apply.lock"

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"state": "never-applied"}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"state": "unknown", "error": "Status file is unreadable"}

    def write(self, state: dict[str, Any]) -> None:
        state = {**state, "updatedAt": datetime.now(UTC).isoformat()}
        descriptor, name = tempfile.mkstemp(prefix=".status.", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            directory_stat = self.directory.stat()
            os.chmod(temporary, 0o660)
            if os.geteuid() == 0:
                os.chown(temporary, 0, directory_stat.st_gid)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def lock(self) -> Iterator[None]:
        with self.lock_path.open("a+") as handle:
            if os.geteuid() == 0:
                os.chmod(self.lock_path, 0o660)
                os.chown(self.lock_path, 0, self.directory.stat().st_gid)
            elif self.lock_path.stat().st_uid == os.geteuid():
                os.chmod(self.lock_path, 0o660)
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def config_hash(config: Config) -> str:
    digest = hashlib.sha256()
    digest.update(f"eduplanner-demo:{__version__}:{POPULATOR_VERSION}\0".encode())
    digest.update(os.getenv("DEMO_BASE_URL", "").encode())
    digest.update(b"\0")
    digest.update(os.getenv("DEMO_LBPLANNER_REF", "unknown").encode())
    digest.update(b"\0")
    for name in ("courses", "users"):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(config.path(name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def apply(
    config: Config,
    adapter: MoodleCLI,
    schema_dir: str | Path,
    state: StateStore,
    *,
    force: bool = False,
) -> dict[str, Any]:
    with state.lock():
        previous = state.read()
        requested_hash: str | None = None
        try:
            requested_hash = config_hash(config)
            manifest_path = state.directory / INTEGRATION_MANIFEST
            manifest_ready = (
                manifest_path.is_file()
                and manifest_path.stat().st_mode & 0o777 == 0o600
            )
            if (
                not force
                and previous.get("state") == "ready"
                and previous.get("hash") == requested_hash
                and manifest_ready
            ):
                Logger.info(f"Configuration unchanged ({requested_hash[:12]}); skipping full reset")
                return previous
            with Logger.stage("Validate configuration and regenerate schemas"):
                parsed = config.read()
                generate_schemas(schema_dir, parsed)
                external_url = base_url()
            state.write({"state": "applying", "hash": requested_hash})
            (state.directory / INTEGRATION_MANIFEST).unlink(missing_ok=True)
            with Logger.stage("Configure Moodle and LB Planner Sync API"):
                environment = adapter.configure(external_url)
                environment["lbPlannerRef"] = os.getenv("DEMO_LBPLANNER_REF", "unknown")
                if Logger.verbose:
                    Logger.debug(f"Moodle diagnostics: {adapter.diagnostics()}")
            adapter.enable_maintenance()
            try:
                with Logger.stage("Delete all non-admin users and courses"):
                    deleted = adapter.reset()
                with Logger.stage(
                    f"Create {len(parsed.courses)} courses and {len(parsed.activities)} activities"
                ):
                    content = adapter.create_content(parsed)
                with Logger.stage(f"Create and enrol {len(parsed.users)} users"):
                    user_ids = adapter.create_users(parsed, content)
                with Logger.stage("Create submissions, quiz attempts, grades, and completion states"):
                    activity_states = adapter.apply_states(parsed, content, user_ids)
            finally:
                adapter.disable_maintenance()
            with Logger.stage("Purge Moodle caches and verify the sync contract"):
                adapter.purge_caches()
                representative = next(iter(user_ids.values()))
                contract = adapter.internal_doctor(representative)
            with Logger.stage("Create private EduPlanner integration manifest"):
                write_integration_manifest(parsed, state, requested_hash)
            result = {
                "state": "ready",
                "hash": requested_hash,
                "environment": environment,
                "counts": {
                    "courses": len(parsed.courses),
                    "activities": len(parsed.activities),
                    "assignments": sum(activity.type.value == "assignment" for activity in parsed.activities),
                    "quizzes": sum(activity.type.value == "quiz" for activity in parsed.activities),
                    "users": len(parsed.users),
                    **activity_states,
                },
                "deleted": deleted,
                "contract": contract,
            }
            state.write(result)
            Logger.success(
                f"Demo ready: {len(parsed.users)} users, {len(parsed.courses)} courses, "
                f"{len(parsed.activities)} activities"
            )
            return result
        except Exception as error:
            state.write(
                {
                    "state": "failed",
                    "hash": previous.get("hash"),
                    **({"requestedHash": requested_hash} if requested_hash else {}),
                    "error": str(error),
                }
            )
            raise


def write_integration_manifest(
    config: DemoConfig,
    state: StateStore,
    configuration_hash: str,
) -> Path:
    """Atomically write the private, token-bearing EduPlanner handoff file.

    The manifest lives only in the container state volume. Its contents are
    consumed by the Serverpod provisioner and must never be printed or added to
    normal status output.
    """
    users: list[dict[str, Any]] = []
    for user in config.users:
        token_result = _local_request(
            "/login/token.php",
            {
                "username": user.id,
                "password": config.password,
                "service": "lb_planner_sync_api",
            },
        )
        token = token_result.get("token") if isinstance(token_result, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"Moodle did not issue a sync token for {user.id}")
        users.append(
            {
                "key": user.id,
                "name": user.name,
                "email": f"{user.id}@example.invalid",
                "role": user.role.value,
                "class": user.clazz,
                "token": token,
            }
        )
    payload = {
        "schemaVersion": 1,
        "configurationHash": configuration_hash,
        "siteUrl": base_url(),
        "users": users,
    }
    descriptor, name = tempfile.mkstemp(prefix=".integration-manifest.", dir=state.directory)
    temporary = Path(name)
    destination = state.directory / INTEGRATION_MANIFEST
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _local_request(path: str, data: dict[str, str]) -> Any:
    parsed = urlparse(base_url())
    port = int(os.getenv("DEMO_INTERNAL_HTTP_PORT", "8080"))
    request_host = parsed.netloc if parsed.scheme == "http" else f"127.0.0.1:{port}"
    for attempt in range(1, 4):
        request = Request(
            f"http://127.0.0.1:{port}{path}",
            data=urlencode(data).encode(),
            headers={
                "Host": request_host,
                "X-Forwarded-Proto": parsed.scheme,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except (URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 3:
                raise
            Logger.warning(f"Moodle HTTP request failed; retrying {path} ({attempt}/3)")
            time.sleep(attempt)
    raise AssertionError("unreachable")


def doctor(config: Config, adapter: MoodleCLI) -> dict[str, Any]:
    parsed = config.read()
    environment = adapter.diagnostics()
    environment["lbPlannerRef"] = os.getenv("DEMO_LBPLANNER_REF", "unknown")
    proxy_mode = urlparse(base_url()).scheme == "https"
    expected = {
        "pluginRelease": "2.0.0",
        "siteUrl": base_url(),
        "reverseProxy": proxy_mode,
        "sslProxy": proxy_mode,
        "webServices": True,
        "restEnabled": True,
        "serviceEnabled": True,
    }
    mismatches = {
        key: {"expected": value, "actual": environment.get(key)}
        for key, value in expected.items()
        if environment.get(key) != value
    }
    if not str(environment.get("moodleRelease", "")).startswith("4.4"):
        mismatches["moodleRelease"] = {
            "expected": "4.4.x",
            "actual": environment.get("moodleRelease"),
        }
    if not environment.get("customFieldsVersion"):
        mismatches["customFieldsVersion"] = {"expected": "installed", "actual": None}
    if mismatches:
        raise RuntimeError(f"Moodle/plugin diagnostics failed: {mismatches}")
    representative = parsed.users[0]
    token_result = _local_request(
        "/login/token.php",
        {
            "username": representative.id,
            "password": parsed.password,
            "service": "lb_planner_sync_api",
        },
    )
    if "token" not in token_result:
        raise RuntimeError(f"Moodle did not issue a sync token: {token_result}")
    resources: dict[str, Any] = {}
    for resource in ("identity", "courses", "assignments", "quizzes"):
        function = f"local_lbplanner_sync_get_{resource}"
        result = _local_request(
            "/webservice/rest/server.php",
            {
                "wstoken": token_result["token"],
                "wsfunction": function,
                "moodlewsrestformat": "json",
            },
        )
        if isinstance(result, dict) and result.get("exception"):
            raise RuntimeError(f"{function} failed: {result.get('message', result)}")
        resources[resource] = result
    identity = resources["identity"]
    if identity.get("contractVersion") != 1 or identity.get("pluginRelease") != "2.0.0":
        raise RuntimeError(f"Unexpected LB Planner identity: {identity}")
    if identity.get("siteUrl") != base_url():
        raise RuntimeError(
            f"Plugin siteUrl {identity.get('siteUrl')!r} does not match DEMO_BASE_URL {base_url()!r}"
        )
    return {
        "user": representative.id,
        "environment": environment,
        "identity": identity,
        "counts": {
            resource: len(value) for resource, value in resources.items() if isinstance(value, list)
        },
    }
