from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .model import ActivityType, Classification, DemoConfig, TaskStatus, UserRole


def course_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Courses",
        "type": "object",
        "required": ["courses"],
        "properties": {
            "courses": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "tasks"],
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["name", "description", "due", "type"],
                                "additionalProperties": False,
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "description": {"type": "string"},
                                    "due": {"type": "integer", "minimum": 0},
                                    "type": {"enum": [value.value for value in ActivityType]},
                                    "classification": {
                                        "type": ["string", "null"],
                                        "enum": [value.value for value in Classification] + [None],
                                    },
                                },
                            },
                        },
                    },
                },
            }
        },
        "additionalProperties": False,
    }


def user_schema(config: DemoConfig) -> dict:
    course_ids = [course.id for course in config.courses]
    task_properties = {
        activity.id: {
            "type": "string",
            "enum": [value.value for value in TaskStatus],
            "title": f"{activity.name} ({activity.course_id})",
        }
        for activity in config.activities
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Users",
        "type": "object",
        "required": ["password", "users"],
        "additionalProperties": False,
        "properties": {
            "password": {"type": "string", "minLength": 1},
            "users": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "role", "courses"],
                    "additionalProperties": False,
                    "allOf": [
                        {
                            "if": {"properties": {"role": {"const": "student"}}},
                            "then": {
                                "required": ["class"],
                                "properties": {"class": {"type": "string", "minLength": 1}},
                            },
                        },
                        {
                            "if": {"properties": {"role": {"const": "teacher"}}},
                            "then": {"properties": {"task-status": {"maxProperties": 0}}},
                        },
                    ],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "role": {"enum": [value.value for value in UserRole]},
                        "class": {"type": ["string", "null"]},
                        "courses": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string", "enum": course_ids},
                        },
                        "task-status": {
                            "type": "object",
                            "properties": task_properties,
                            "additionalProperties": False,
                        },
                    },
                },
            },
        },
    }


def generate_schemas(output: str | Path, config: DemoConfig) -> list[Path]:
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    generated = []
    for name, schema in (
        ("courses.yml.schema.json", course_schema()),
        ("users.yml.schema.json", user_schema(config)),
    ):
        path = directory / name
        payload = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == payload:
            generated.append(path)
            continue
        stat = path.stat() if path.exists() else None
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if stat:
                os.chmod(temporary, stat.st_mode)
                if os.geteuid() == 0:
                    os.chown(temporary, stat.st_uid, stat.st_gid)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        generated.append(path)
    return generated
