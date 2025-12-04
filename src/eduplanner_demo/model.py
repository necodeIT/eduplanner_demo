from enum import StrEnum


def toId(name: str) -> str:
    return name.lower().replace(" ", "_")


class TaskStatus(StrEnum):
    """
    Enumeration representing the possible status values for a task.
    This enum defines the lifecycle states that a task can be in within the
    education planning system.
    Attributes:
        PENDING (str): Task has been created but not yet completed.
        COMPLETED (str): Task has been finished successfully.
        OVERDUE (str): Task has passed its due date without completion.
        SUBMITTED (str): Task has been submitted for review or grading.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    SUBMITTED = "submitted"


class Task:
    """
    A class representing a task in the education planner.

    Attributes:
        name (str): The name of the task.
        parent (str): The id of the parent course this task belongs to.
        due (int): The time in days until the task is due. (relative to time of creation)
        description (str): A detailed description of the task.
        id (str): A unique identifier generated from parent and name using toId function.
    """

    name: str
    """The name of the task."""
    parent: str
    """The id of the parent course this task belongs to."""
    due: int
    """The time in days until the task is due. (relative to time of creation)"""
    description: str
    """A detailed description of the task."""
    id: str
    """A unique identifier generated from parent and name using toId function."""

    def __init__(self, name: str, parent: str, due: int, description: str):
        self.name = name
        self.parent = parent
        self.due = due
        self.description = description
        self.id = toId(f"{parent}.{name}")


class Course:
    """
    Represents a course with associated tasks.

    A Course object encapsulates information about an educational course,
    including its name, automatically generated ID, and a collection of tasks.

    Attributes:
        name (str): The name of the course.
        id: The automatically generated ID based on the course name.
        tasks (list[Task]): The list of tasks belonging to this course.
    """

    name: str
    """The name of the course."""
    id: str
    """The automatically generated ID based on the course name."""
    tasks: list[Task]
    """The list of tasks belonging to this course."""

    def __init__(self, name: str, tasks: list[Task]):
        self.name = name
        self.id = toId(name)
        self.tasks = tasks


class Capability(StrEnum):
    """
    Enumeration of user capabilities in the education planning system.

    This enum defines the different types of users and their associated roles
    within the system, determining what actions and resources each user type
    can access.

    Attributes:
        STUDENT: Regular student user with basic access permissions
        TEACHER: Instructor user with teaching and classroom management permissions
        SLOTMASTER: Administrative user with scheduling and time slot management permissions
    """

    STUDENT = "student"
    TEACHER = "teacher"
    SLOTMASTER = "slotmaster"


class Clazz(StrEnum):
    """
    Enumeration representing class/grade levels in an educational system.

    Each enum value represents a specific class level where:
    - The number (1-5) indicates the grade level
    - The letter (A/B) indicates the class section within that grade

    Attributes:
        A1 (str): Class 1A
        B1 (str): Class 1B
        A2 (str): Class 2A
        B2 (str): Class 2B
        A3 (str): Class 3A
        B3 (str): Class 3B
        A4 (str): Class 4A
        B4 (str): Class 4B
        A5 (str): Class 5A
        B5 (str): Class 5B
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


class User:
    """
    Represents a user in the educational planning system.

    Attributes:
        name (str): The user's name.
        capabilities (list[Capability]): List of capabilities the user possesses.
        clazz (Clazz | None): The class/course the user is enrolled in.
        token (str): Authentication token for the user.
        task_status (dict[Task, TaskStatus]): Task completion status mapping.
    """

    name: str
    """The user's name."""
    capabilities: list[Capability]
    """List of capabilities the user possesses."""
    clazz: Clazz | None
    """The class the user is enrolled in."""
    token: str
    """Authentication token for the user."""
    task_status: dict[Task, TaskStatus]
    """Task completion status mapping."""

    def __init__(
        self,
        name: str,
        capabilities: list[Capability],
        clazz: Clazz | None,
        token: str,
        task_status: dict[Task, TaskStatus],
    ):
        self.name = name
        self.capabilities = capabilities
        self.clazz = clazz
        self.token = token
        self.task_status = task_status
