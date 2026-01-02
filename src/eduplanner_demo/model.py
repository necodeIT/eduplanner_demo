from enum import IntEnum, StrEnum
from dataclasses import dataclass
from abc import ABC
from datetime import datetime, timedelta, UTC, timezone

from .logger import Logger

NOW = datetime.now(UTC)

def toId(name: str) -> str:
    return name.lower().replace(" ", "_")

class MoodleObject(ABC):
    moodleid_: int | None = None # TODO: figure out a way to do this with a proper private variable and such

    @property
    def moodleid(self) -> int:
        """ the moodle-internal ID this object has """
        assert self.moodleid_ is not None # TODO: proper exception
        return self.moodleid_

    @moodleid.setter
    def moodleid(self, i: int) -> None:
        assert self.moodleid_ is None # TODO: proper exception
        self.moodleid_ = i


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


class Weekday(IntEnum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7

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

    A1 = "1AHIT"
    B1 = "1BHIT"
    A2 = "2AHIT"
    B2 = "2BHIT"
    A3 = "3AHIT"
    B3 = "3BHIT"
    A4 = "4AHIT"
    B4 = "4BHIT"
    A5 = "5AHIT"
    B5 = "5BHIT"


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
    task_status: dict[str, TaskStatus]
    """Task completion status mapping."""

    @property
    def id(self) -> str:
        """A unique identifier generated from the user's name."""
        return toId(self.name)

@dataclass
class SlotMapping(MoodleObject):
    """
    Represents a mapping between a slot and a user or group.
    """
    course: Course
    """The name of the course this slot is mapped to."""
    clazz: Clazz
    """The class this slot is mapped to."""

@dataclass
class Slot(MoodleObject):
    """
    Represents an eduplanner slot
    """
    disambiguate: int
    """An integer to disambiguate slots with the same time and place."""
    startunit: int
    """The starting unit of the slot (1-16)."""
    duration: int
    """The duration of the slot (may not exceed 16 when added to startunit)."""
    weekday: Weekday
    """The weekday of the slot (e.g., 'monday', 'tuesday')."""
    room: str
    """The room where the slot takes place."""
    capacity: int
    """How many students can fit into this slot."""
    mappings: list[SlotMapping]
    """The list of class/course mappings for this slot."""
    supervisors: list[User]
    """IDs of the users that are supervisors for this slot."""

    @property
    def id(self) -> str:
        """A unique identifier generated from place and time."""
        return toId(f"{self.room}.{self.disambiguate}")

@dataclass
class Deadline(MoodleObject):
    """
    Represents an eduplanner deadline
    """
    task: Task
    """The task this deadline is associated with."""
    deadlinestart: int
    """The start of the deadline in "days after now"."""
    duration: int
    """The end of the deadline in "days after now"."""
    
    

@dataclass
class Plan(MoodleObject):
    """
    Represents an eduplanner plan
    """
    name: str
    """The name of the plan."""
    deadlines: list[Deadline]
    """Deadlines as slotid: (deadlinestart, deadlineend), where start and end are in "days after now"."""
    owner: User
    """The owner of the plan."""
    members: list[User]
    """The members of the plan."""
    def __post_init__(self):
        # make sure no task has two mappings
        usedtasks = []
        for deadline in self.deadlines:
            assert deadline.task not in usedtasks
            usedtasks.append(deadline.task)




def find_user(users: list[User], usrid: str) -> User:
    """Finds a user by id in a list of users.

    :param list[User] users: The list of users to search.
    :param str usrid: The id of the user to find.
    :return User | None: The found User object or None if not found.
    """
    for user in users:
        if user.id == usrid:
            return user
    Logger.error(f"user with id '{usrid}' not found")
    exit(1)

def find_task(tasks: list[Task], id: str) -> Task:
    """Finds a task by ID in a list of tasks.

    :param list[Task] tasks: The list of tasks to search.
    :param str id: The ID of the task to find.
    :return Task | None: The found Task object or None if not found.
    """
    for task in tasks:
        if task.id == id:
            return task
    Logger.error(f"task with id '{id}' not found")
    exit(1)

def find_course(courses: list[Course], crid: str) -> Course:
    """Finds a course by ID in a list of courses.

    :param list[Course] courses: The list of courses to search.
    :param str crid: The ID of the course to find.
    :return Course: The found Course object.
    """
    for course in courses:
        if course.id == crid:
            return course
    Logger.error(f"course with id '{crid}' not found")
    exit(1)