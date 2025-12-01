from enum import Enum


def toId(name: str) -> str:
    return name.lower().replace(" ", "")


class TaskStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    SUBMITTED = "submitted"


class Task:
    def __init__(self, name: str, parent: str, due: int, description: str):
        self.name = name
        self.parent = parent
        self.due = due
        self.description = description
        self.id = toId(f"{parent}.{name}")


class Course:
    def __init__(self, name: str, tasks: list[Task]):
        self.name = name
        self.id = toId(name)
        self.tasks = tasks


class Capability(Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    SLOTMASTER = "slotmaster"


class Clazz(Enum):
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
