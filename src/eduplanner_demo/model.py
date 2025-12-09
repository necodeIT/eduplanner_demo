from enum import StrEnum
from dataclasses import dataclass
from abc import ABC
from datetime import datetime, timedelta, UTC, timezone

NOW = datetime.now(UTC)

def toId(name: str) -> str:
    return name.lower().replace(" ", "_")

class MoodleObject(ABC):
    __slots__ = ("__moodleid",)
    __moodleid: int | None

    @property
    def moodleid(self) -> int:
        """ the moodle-internal ID this object has """
        assert self.__moodleid is not None # TODO: proper exception
        return self.__moodleid

    @moodleid.setter
    def moodleid(self, i: int) -> None:
        assert self.__moodleid is None # TODO: proper exception
        self.__moodleid = i


class TaskStatus(StrEnum):
    """
    Enumeration representing the possible status values for a task.
    This enum defines the lifecycle states that a task can be in within the
    education planning system.
    """

    PENDING = "pending"
    """Task has been created but not yet completed."""
    COMPLETED = "completed"
    """Task has been finished successfully."""
    OVERDUE = "overdue"
    """Task has passed its due date without completion."""
    SUBMITTED = "submitted"
    """Task has been submitted for review or grading."""


@dataclass
class Task(MoodleObject):
    """
    A class representing a moodle assignment.
    """

    name: str
    """The name of the task."""
    parent: str
    """The id of the parent course this task belongs to."""
    due: int
    """The time in days until the task is due. (relative to time of creation)"""
    description: str
    """A detailed description of the task."""

    @property
    def absdue(self, tz: timezone = UTC) -> int:
        """ a UNIX timestamp corresponding to self.due """
        return (int)((NOW.astimezone(tz) + timedelta(days=self.due)).timestamp())

    @property
    def id(self) -> str:
        """A unique identifier generated from parent and name using toId function."""
        return toId(f"{self.parent}.{self.name}")


@dataclass
class Course(MoodleObject):
    """
    Represents a course with associated tasks.

    A Course object encapsulates information about an educational course,
    including its name, automatically generated ID, and a collection of tasks.
    """

    name: str
    """The name of the course."""
    tasks: list[Task]
    """The list of tasks belonging to this course."""

    @property
    def id(self) -> str:
        """The automatically generated ID based on the course name."""
        return toId(self.name)


class Capability(StrEnum):
    """
    Enumeration of user capabilities in the education planning system.

    This enum defines the different types of users and their associated roles
    within the system, determining what actions and resources each user type
    can access.
    """

    STUDENT = "student"
    """Regular student user with basic access permissions"""
    TEACHER = "teacher"
    """Instructor user with teaching and classroom management permissions"""
    SLOTMASTER = "slotmaster"
    """Administrative user with scheduling and time slot management permissions"""


class Clazz(StrEnum):
    """
    Enumeration representing class/grade levels in an educational system.

    Each enum value represents a specific class level where:
    - The number (1-5) indicates the grade level
    - The letter (A/B) indicates the class section within that grade
    """

    A1 = "1A"
    B1 = "1B"
    A2 = "2A"
    B2 = "2B"
    A3 = "3A"
    B3 = "3B"
    A4 = "4A"
    B4 = "4B"
    A5 = "5A"
    B5 = "5B"


@dataclass
class User(MoodleObject):
    """
    Represents a user in the educational planning system.
    """

    name: str
    """The user's name."""
    capabilities: list[Capability]
    """List of capabilities the user possesses."""
    clazz: Clazz | None
    """The class the user is enrolled in."""
    token: str
    """Authentication token for the user."""
    task_status: dict[str, TaskStatus]
    """Task completion status mapping."""

    # TODO: plan
