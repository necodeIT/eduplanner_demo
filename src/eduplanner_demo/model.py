from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class ActivityType(StrEnum):
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"


class Classification(StrEnum):
    GK = "GK"
    EK = "EK"
    TEST = "TEST"
    M = "M"


class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"


class TaskStatus(StrEnum):
    SUBMITTED = "submitted"
    COMPLETED = "completed"


def to_id(value: str) -> str:
    """Return a stable, Moodle-safe identifier derived from display text."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


@dataclass(slots=True)
class Activity:
    name: str
    course_id: str
    due_days: int
    description: str
    type: ActivityType
    classification: Classification | None = None
    moodle_id: int | None = field(default=None, init=False)
    course_module_id: int | None = field(default=None, init=False)

    @property
    def id(self) -> str:
        return f"{self.course_id}.{to_id(self.name)}"

    def deadline(self, now: datetime | None = None) -> int:
        base = now or datetime.now(UTC)
        return int((base + timedelta(days=self.due_days)).timestamp())


@dataclass(slots=True)
class Course:
    name: str
    activities: list[Activity]
    moodle_id: int | None = field(default=None, init=False)

    @property
    def id(self) -> str:
        return to_id(self.name)


@dataclass(slots=True)
class User:
    name: str
    role: UserRole
    courses: list[str]
    clazz: str | None
    task_status: dict[str, TaskStatus]
    moodle_id: int | None = field(default=None, init=False)

    @property
    def id(self) -> str:
        return to_id(self.name)


@dataclass(slots=True)
class DemoConfig:
    password: str
    users: list[User]
    courses: list[Course]

    @property
    def activities(self) -> list[Activity]:
        return [activity for course in self.courses for activity in course.activities]

    def as_wire_dict(self) -> dict:
        """Serialize the validated model for the Moodle PHP bridge."""
        return {
            "password": self.password,
            "courses": [
                {
                    "id": course.id,
                    "name": course.name,
                    "activities": [
                        {
                            "id": activity.id,
                            "name": activity.name,
                            "description": activity.description,
                            "deadline": activity.deadline(),
                            "type": activity.type.value,
                            "classification": (
                                activity.classification.value if activity.classification else None
                            ),
                        }
                        for activity in course.activities
                    ],
                }
                for course in self.courses
            ],
            "users": [
                {
                    "id": user.id,
                    "name": user.name,
                    "role": user.role.value,
                    "courses": user.courses,
                    "class": user.clazz,
                    "taskStatus": {key: value.value for key, value in user.task_status.items()},
                }
                for user in self.users
            ],
        }
