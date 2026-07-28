from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eduplanner_demo.agent import AgentContext, wait_for_stable_hash
from eduplanner_demo.config import Config
from eduplanner_demo.populate import StateStore

from .test_config import valid_data


def context(tmp_path: Path):
    courses, users = valid_data()
    config_dir = tmp_path / "config"
    schema_dir = tmp_path / "schema"
    state_dir = tmp_path / "state"
    config_dir.mkdir()
    (config_dir / "courses.yml").write_text(yaml.safe_dump(courses, sort_keys=False))
    (config_dir / "users.yml").write_text(yaml.safe_dump(users, sort_keys=False))
    queued: list[bool] = []
    agent = AgentContext(Config(config_dir), schema_dir, StateStore(state_dir), lambda: queued.append(True))
    return agent, courses, users, queued


def test_agent_read_validate_save_and_queue(tmp_path: Path) -> None:
    agent, courses, users, queued = context(tmp_path)
    assert agent.dispatch({"operation": "read"})["courses"] == courses
    assert agent.dispatch({"operation": "validate", "courses": courses, "users": users})["valid"]
    users["password"] = "updated"
    saved = agent.dispatch({"operation": "save", "courses": courses, "users": users})
    assert saved["saved"] and queued == [True]
    assert agent.dispatch({"operation": "read"})["users"]["password"] == "updated"


def test_agent_rejects_unknown_operations(tmp_path: Path) -> None:
    agent, _, _, _ = context(tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        agent.dispatch({"operation": "shell"})


def test_debounce_waits_for_the_last_hash(tmp_path: Path) -> None:
    agent, _, _, _ = context(tmp_path)
    values = iter(["first", "second", "second", "second", "second"])
    now = [0.0]

    def pause(seconds: float) -> None:
        now[0] += seconds

    result = wait_for_stable_hash(
        agent.config,
        quiet_seconds=0.2,
        poll_seconds=0.1,
        reader=lambda config: next(values),
        clock=lambda: now[0],
        pause=pause,
    )
    assert result == "second"
