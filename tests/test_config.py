from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from eduplanner_demo.config import Config, ConfigError
from eduplanner_demo.adapter_moodlecli import MoodleCLI
from eduplanner_demo.logger import redact
from eduplanner_demo.populate import base_url, config_hash
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
