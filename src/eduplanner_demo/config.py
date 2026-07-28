from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .model import (
    Activity,
    ActivityType,
    Classification,
    Course,
    DemoConfig,
    TaskStatus,
    User,
    UserRole,
    to_id,
)


class ConfigError(ValueError):
    """A user-facing configuration validation error."""


class Config:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory or os.getenv("DEMO_CONFIG_DIR", self.find_directory())).resolve()
        if not self.directory.is_dir():
            raise ConfigError(f"Configuration directory does not exist: {self.directory}")

    @staticmethod
    def find_directory() -> Path:
        candidates = [
            Path(__file__).resolve().parents[2] / "config",
            Path.home() / ".config" / "eduplanner_demo",
            Path("/etc/eduplanner_demo"),
        ]
        return next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])

    def path(self, name: str) -> Path:
        path = self.directory / f"{name}.yml"
        if not path.is_file():
            raise ConfigError(f"Missing configuration file: {path}")
        return path

    def raw(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._read_yaml(self.path("courses")), self._read_yaml(self.path("users"))

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ConfigError(f"Invalid YAML in {path.name}: {error}") from error
        if not isinstance(value, dict):
            raise ConfigError(f"{path.name} must contain a YAML object")
        return value

    def read(self) -> DemoConfig:
        courses, users = self.raw()
        return self.from_data(courses, users)

    @classmethod
    def from_data(cls, courses_data: dict[str, Any], users_data: dict[str, Any]) -> DemoConfig:
        courses = cls._parse_courses(courses_data)
        users = cls._parse_users(users_data, courses)
        password = users_data.get("password")
        if not isinstance(password, str) or not password:
            raise ConfigError("users.yml: password must be a non-empty string")
        return DemoConfig(password=password, users=users, courses=courses)

    @classmethod
    def _parse_courses(cls, data: dict[str, Any]) -> list[Course]:
        rows = data.get("courses")
        if not isinstance(rows, list) or not rows:
            raise ConfigError("courses.yml: courses must be a non-empty list")
        courses: list[Course] = []
        course_ids: set[str] = set()
        activity_ids: set[str] = set()
        for index, row in enumerate(rows):
            location = f"courses[{index}]"
            if not isinstance(row, dict):
                raise ConfigError(f"{location} must be an object")
            name = cls._string(row, "name", location)
            course_id = to_id(name)
            if not course_id:
                raise ConfigError(f"{location}.name does not produce a usable ID")
            if course_id in course_ids:
                raise ConfigError(f"Duplicate or colliding course ID: {course_id}")
            course_ids.add(course_id)
            task_rows = row.get("tasks")
            if not isinstance(task_rows, list):
                raise ConfigError(f"{location}.tasks must be a list")
            activities: list[Activity] = []
            for task_index, task in enumerate(task_rows):
                task_location = f"{location}.tasks[{task_index}]"
                if not isinstance(task, dict):
                    raise ConfigError(f"{task_location} must be an object")
                task_name = cls._string(task, "name", task_location)
                try:
                    activity_type = ActivityType(task.get("type"))
                except (TypeError, ValueError) as error:
                    raise ConfigError(
                        f"{task_location}.type must be assignment or quiz"
                    ) from error
                classification_value = task.get("classification")
                try:
                    classification = (
                        Classification(classification_value)
                        if classification_value not in (None, "")
                        else None
                    )
                except ValueError as error:
                    raise ConfigError(
                        f"{task_location}.classification must be GK, EK, TEST, M, or null"
                    ) from error
                due = task.get("due")
                if not isinstance(due, int) or isinstance(due, bool) or due < 0:
                    raise ConfigError(f"{task_location}.due must be a non-negative integer")
                description = task.get("description", "")
                if not isinstance(description, str):
                    raise ConfigError(f"{task_location}.description must be a string")
                activity = Activity(
                    name=task_name,
                    course_id=course_id,
                    due_days=due,
                    description=description,
                    type=activity_type,
                    classification=classification,
                )
                if activity.id in activity_ids:
                    raise ConfigError(f"Duplicate or colliding task ID: {activity.id}")
                activity_ids.add(activity.id)
                activities.append(activity)
            courses.append(Course(name=name, activities=activities))
        return courses

    @classmethod
    def _parse_users(cls, data: dict[str, Any], courses: list[Course]) -> list[User]:
        rows = data.get("users")
        if not isinstance(rows, list) or not rows:
            raise ConfigError("users.yml: users must be a non-empty list")
        course_ids = {course.id for course in courses}
        activities = {activity.id: activity for course in courses for activity in course.activities}
        users: list[User] = []
        user_ids: set[str] = set()
        for index, row in enumerate(rows):
            location = f"users[{index}]"
            if not isinstance(row, dict):
                raise ConfigError(f"{location} must be an object")
            name = cls._string(row, "name", location)
            user_id = to_id(name)
            if not user_id:
                raise ConfigError(f"{location}.name does not produce a usable username")
            if user_id in {"admin", "guest"}:
                raise ConfigError(f"{location}.name produces reserved Moodle username {user_id}")
            if user_id in user_ids:
                raise ConfigError(f"Duplicate or colliding username: {user_id}")
            user_ids.add(user_id)
            try:
                role = UserRole(row.get("role"))
            except (TypeError, ValueError) as error:
                raise ConfigError(f"{location}.role must be student or teacher") from error
            clazz = row.get("class")
            if role is UserRole.STUDENT and (not isinstance(clazz, str) or not clazz.strip()):
                raise ConfigError(f"{location}.class is required for students")
            if clazz is not None and not isinstance(clazz, str):
                raise ConfigError(f"{location}.class must be a string or null")
            enrolled = row.get("courses")
            if not isinstance(enrolled, list) or not enrolled:
                raise ConfigError(f"{location}.courses must be a non-empty list")
            if len(enrolled) != len(set(enrolled)):
                raise ConfigError(f"{location}.courses contains duplicates")
            unknown_courses = set(enrolled) - course_ids
            if unknown_courses:
                raise ConfigError(
                    f"{location}.courses contains unknown IDs: {', '.join(sorted(unknown_courses))}"
                )
            raw_status = row.get("task-status", {})
            if not isinstance(raw_status, dict):
                raise ConfigError(f"{location}.task-status must be an object")
            if role is UserRole.TEACHER and raw_status:
                raise ConfigError(f"{location}.task-status is only supported for students")
            statuses: dict[str, TaskStatus] = {}
            for activity_id, status_value in raw_status.items():
                activity = activities.get(activity_id)
                if activity is None:
                    raise ConfigError(f"{location}.task-status references unknown task {activity_id}")
                if activity.course_id not in enrolled:
                    raise ConfigError(
                        f"{location}.task-status references {activity_id}, but its course is not enrolled"
                    )
                try:
                    statuses[activity_id] = TaskStatus(status_value)
                except (TypeError, ValueError) as error:
                    raise ConfigError(
                        f"{location}.task-status.{activity_id} must be submitted or completed"
                    ) from error
            users.append(
                User(
                    name=name,
                    role=role,
                    courses=list(enrolled),
                    clazz=clazz.strip() if isinstance(clazz, str) else None,
                    task_status=statuses,
                )
            )
        return users

    @staticmethod
    def _string(data: dict[str, Any], key: str, location: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{location}.{key} must be a non-empty string")
        return value.strip()

    def save(self, courses: dict[str, Any], users: dict[str, Any]) -> DemoConfig:
        """Validate and atomically save both documents, preserving ownership and mode."""
        parsed = self.from_data(courses, users)
        self._atomic_yaml(self.path("courses"), courses)
        self._atomic_yaml(self.path("users"), users)
        return parsed

    @staticmethod
    def _atomic_yaml(path: Path, value: dict[str, Any]) -> None:
        stat = path.stat()
        payload = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, stat.st_mode)
            if os.geteuid() == 0:
                os.chown(temporary, stat.st_uid, stat.st_gid)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
