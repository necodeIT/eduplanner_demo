from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from typing import Self
from urllib.error import HTTPError, URLError

import pytest
import yaml

from eduplanner_demo.adapter_moodlecli import MoodleCLI, MoodleError
from eduplanner_demo.config import Config, ConfigError
from eduplanner_demo.logger import redact
from eduplanner_demo.populate import (
    INTERNAL_HTTP_ATTEMPTS,
    StateStore,
    _local_request,
    base_url,
    config_hash,
    write_integration_manifest,
)
from eduplanner_demo.schemagen import generate_schemas


def valid_data() -> tuple[dict, dict]:
    courses = {
        "courses": [
            {
                "name": "Computer Science",
                "tasks": [
                    {
                        "name": "Final Quiz",
                        "description": "A quiz",
                        "due": 3,
                        "type": "quiz",
                        "classification": "TEST",
                    },
                    {
                        "name": "Project",
                        "description": "An assignment",
                        "due": 5,
                        "type": "assignment",
                        "classification": None,
                    },
                ],
            }
        ]
    }
    users = {
        "password": "public-password",
        "users": [
            {
                "name": "Alice Student",
                "role": "student",
                "class": "1AHIT",
                "courses": ["computer_science"],
                "task-status": {"computer_science.final_quiz": "completed"},
            },
            {
                "name": "Taylor Teacher",
                "role": "teacher",
                "courses": ["computer_science"],
            },
        ],
    }
    return courses, users


def write_config(directory: Path, courses: dict, users: dict) -> Config:
    (directory / "courses.yml").write_text(yaml.safe_dump(courses, sort_keys=False))
    (directory / "users.yml").write_text(yaml.safe_dump(users, sort_keys=False))
    return Config(directory)


def test_parses_new_contract_and_wire_payload(tmp_path: Path) -> None:
    courses, users = valid_data()
    parsed = write_config(tmp_path, courses, users).read()
    assert parsed.courses[0].id == "computer_science"
    assert [activity.type.value for activity in parsed.activities] == ["quiz", "assignment"]
    assert parsed.activities[0].classification.value == "TEST"
    wire = parsed.as_wire_dict()
    assert wire["users"][0]["id"] == "alice_student"
    assert wire["users"][0]["taskStatus"] == {"computer_science.final_quiz": "completed"}


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda courses, users: courses["courses"][0]["tasks"][0].update(type="exam"), "assignment or quiz"),
        (lambda courses, users: users["users"][0].pop("class"), "class is required"),
        (
            lambda courses, users: users["users"][0]["courses"].append("unknown"),
            "unknown IDs",
        ),
        (
            lambda courses, users: users["users"][0]["task-status"].update(
                {"computer_science.project": "pending"}
            ),
            "submitted or completed",
        ),
    ],
)
def test_rejects_invalid_contract(change, message: str) -> None:
    courses, users = valid_data()
    change(courses, users)
    with pytest.raises(ConfigError, match=message):
        Config.from_data(courses, users)


def test_rejects_slug_collisions() -> None:
    courses, users = valid_data()
    courses["courses"].append({"name": "Computer--Science", "tasks": []})
    with pytest.raises(ConfigError, match="colliding course ID"):
        Config.from_data(courses, users)


def test_schemas_are_deterministic_and_cross_reference_tasks(tmp_path: Path) -> None:
    courses, users = valid_data()
    parsed = Config.from_data(courses, users)
    first = generate_schemas(tmp_path, parsed)
    payloads = [path.read_bytes() for path in first]
    second = generate_schemas(tmp_path, parsed)
    assert payloads == [path.read_bytes() for path in second]
    user_schema = json.loads((tmp_path / "users.yml.schema.json").read_text())
    task_properties = user_schema["properties"]["users"]["items"]["properties"]["task-status"]["properties"]
    assert set(task_properties) == {"computer_science.final_quiz", "computer_science.project"}


def test_hash_changes_with_config_plugin_ref_and_redaction_hides_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    courses, users = valid_data()
    config = write_config(tmp_path, courses, users)
    monkeypatch.setenv("DEMO_LBPLANNER_REF", "2.0.0")
    before = config_hash(config)
    monkeypatch.setenv("DEMO_LBPLANNER_REF", "0123456789abcdef")
    assert config_hash(config) != before
    monkeypatch.setenv("DEMO_LBPLANNER_REF", "2.0.0")
    users["password"] = "changed"
    config.save(courses, users)
    assert config_hash(config) != before
    message = redact('password=secret token: abc wstoken=def {"privateToken":"ghi"}')
    assert all(secret not in message for secret in ("secret", "abc", "def", "ghi"))


def test_save_rejects_candidate_before_replacing_files(tmp_path: Path) -> None:
    courses, users = valid_data()
    config = write_config(tmp_path, courses, users)
    original = config.path("users").read_text()
    users["users"][0]["courses"] = ["missing"]
    with pytest.raises(ConfigError):
        config.save(courses, users)
    assert config.path("users").read_text() == original


def test_save_preserves_file_modes(tmp_path: Path) -> None:
    courses, users = valid_data()
    config = write_config(tmp_path, courses, users)
    os.chmod(config.path("courses"), 0o640)
    os.chmod(config.path("users"), 0o600)
    config.save(courses, users)
    assert config.path("courses").stat().st_mode & 0o777 == 0o640
    assert config.path("users").stat().st_mode & 0o777 == 0o600


def test_private_integration_manifest_contains_every_configured_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    courses, users = valid_data()
    parsed = Config.from_data(courses, users)
    state = StateStore(tmp_path / "state")
    monkeypatch.setenv("DEMO_BASE_URL", "http://localhost:420")
    tokens = {
        "alice_student": "private-alice_student",
        "taylor_teacher": "private-taylor_teacher",
    }
    manifest_path = write_integration_manifest(
        parsed,
        state,
        "configuration-hash",
        tokens,
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert manifest["schemaVersion"] == 1
    assert manifest["configurationHash"] == "configuration-hash"
    assert [row["key"] for row in manifest["users"]] == [
        "alice_student",
        "taylor_teacher",
    ]
    assert manifest["users"][0]["email"] == "alice_student@example.invalid"
    assert manifest["users"][0]["token"] == "private-alice_student"

    first_bytes = manifest_path.read_bytes()
    write_integration_manifest(parsed, state, "configuration-hash", tokens)
    assert manifest_path.read_bytes() == first_bytes

    rotated_tokens = {key: f"rotated-{key}" for key in tokens}
    write_integration_manifest(
        parsed,
        state,
        "configuration-hash",
        rotated_tokens,
    )
    rotated = json.loads(manifest_path.read_text())
    assert rotated["users"][0]["token"] == "rotated-alice_student"
    assert [{**row, "token": None} for row in rotated["users"]] == [
        {**row, "token": None} for row in manifest["users"]
    ]


def test_personal_tokens_use_moodle_cli_before_http_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = MoodleCLI(tmp_path)
    received: dict[str, dict[str, int]] = {}

    def run_php(body: str, payload: dict[str, dict[str, int]]) -> dict[str, str]:
        assert "generate_token_for_current_user" in body
        received.update(payload)
        return {key: f"private-{key}" for key in payload["userIds"]}

    monkeypatch.setattr(adapter, "run_php", run_php)
    assert adapter.create_personal_tokens({"alice": 3, "teacher": 4}) == {
        "alice": "private-alice",
        "teacher": "private-teacher",
    }
    assert received == {"userIds": {"alice": 3, "teacher": 4}}


def test_personal_tokens_reject_incomplete_or_empty_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = MoodleCLI(tmp_path)
    monkeypatch.setattr(adapter, "run_php", lambda *args, **kwargs: {"alice": ""})
    with pytest.raises(MoodleError, match="invalid personal token"):
        adapter.create_personal_tokens({"alice": 3})

    monkeypatch.setattr(adapter, "run_php", lambda *args, **kwargs: {})
    with pytest.raises(MoodleError, match="incomplete personal-token set"):
        adapter.create_personal_tokens({"alice": 3})


class _JsonResponse:
    """Minimal context-managed response used by internal HTTP tests."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_internal_http_retries_transient_status_without_logging_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_BASE_URL", "http://localhost:420")
    attempts = 0
    delays: list[int] = []
    private_body = b'{"token":"must-not-appear"}'

    def transient_then_ready(*args: object, **kwargs: object) -> _JsonResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise HTTPError(
                "http://127.0.0.1/login/token.php",
                503,
                "unavailable",
                {},
                BytesIO(private_body),
            )
        return _JsonResponse(b'{"token":"issued-token"}')

    monkeypatch.setattr("eduplanner_demo.populate.urlopen", transient_then_ready)
    monkeypatch.setattr("eduplanner_demo.populate.time.sleep", delays.append)

    assert _local_request("/login/token.php", {"password": "private"}) == {
        "token": "issued-token"
    }
    assert attempts == 3
    assert delays == [1, 2]


def test_internal_http_fails_fast_and_redacts_permanent_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_BASE_URL", "http://localhost:420")

    def rejected(*args: object, **kwargs: object) -> _JsonResponse:
        raise HTTPError(
            "http://127.0.0.1/login/token.php",
            403,
            "forbidden",
            {},
            BytesIO(b'{"token":"private-response-token"}'),
        )

    monkeypatch.setattr("eduplanner_demo.populate.urlopen", rejected)
    with pytest.raises(RuntimeError, match="HTTP 403") as raised:
        _local_request("/login/token.php", {"password": "private-form-password"})
    assert "private-response-token" not in str(raised.value)
    assert "private-form-password" not in str(raised.value)


def test_internal_http_exhaustion_has_stable_sanitized_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_BASE_URL", "http://localhost:420")
    monkeypatch.setattr(
        "eduplanner_demo.populate.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            URLError("private network detail")
        ),
    )
    monkeypatch.setattr("eduplanner_demo.populate.time.sleep", lambda _: None)

    with pytest.raises(
        RuntimeError, match=f"after {INTERNAL_HTTP_ATTEMPTS} attempts"
    ) as raised:
        _local_request("/login/token.php", {"password": "private-form-password"})
    assert "private network detail" not in str(raised.value)
    assert "private-form-password" not in str(raised.value)


def test_repository_sample_has_migrated_legacy_exams_and_users() -> None:
    repository = Path(__file__).resolve().parents[1]
    courses = yaml.safe_load((repository / "config/courses.yml").read_text())
    users = yaml.safe_load((repository / "config/users.yml").read_text())
    tasks = [task for course in courses["courses"] for task in course["tasks"]]
    assert all(task["type"] in {"assignment", "quiz"} for task in tasks)
    assert all(task.get("classification") == "TEST" for task in tasks if "Exam" in task["name"])
    assert all("capabilities" not in user and "role" in user and "courses" in user for user in users["users"])


@pytest.mark.parametrize(
    "value",
    [
        "http://school.example",
        "https://school.example/",
        "https://user@school.example",
        "https://school.example/path",
        "http://localhost:420/path",
    ],
)
def test_base_url_rejects_non_origin_or_remote_http_url(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DEMO_BASE_URL", value)
    with pytest.raises(ConfigError):
        base_url()


@pytest.mark.parametrize(
    "value",
    ["https://school.example", "http://localhost:420", "http://127.0.0.1:420"],
)
def test_base_url_accepts_https_and_loopback_http(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DEMO_BASE_URL", value)
    assert base_url() == value


def test_moodle_origin_switch_is_persisted_without_duplicate_blocks(tmp_path: Path) -> None:
    config_php = tmp_path / "config.php"
    config_php.write_text("<?php\n$CFG = new stdClass();\nrequire_once(__DIR__ . '/lib/setup.php');\n")
    adapter = MoodleCLI(tmp_path)

    assert adapter._configure_origin("http://localhost:420") is False
    local = config_php.read_text()
    assert "$CFG->wwwroot = 'http://localhost:420';" in local
    assert "$CFG->reverseproxy = false;" in local

    assert adapter._configure_origin("https://school.example") is True
    proxied = config_php.read_text()
    assert proxied.count("BEGIN EDUPLANNER DEMO ORIGIN") == 1
    assert "$CFG->wwwroot = 'https://school.example';" in proxied
    assert "$CFG->reverseproxy = true;" in proxied
