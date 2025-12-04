from .model import Capability, Clazz, Course, TaskStatus
from .config import Config
from os.path import join as pathjoin

config = Config()

courses = config.read_courses_config()

def schemagen(courses: list[Course], dp: str) -> None:
    """Generates schema files to a folder

    :param list[Course] courses: existing courses to take into account
    :param str dp: directory path to save schema files to
    """

    status_props = {
        task.id: {
            "type": "string",
            "description": task.description.strip(),
            "title": f"{task.name} ({course.name.strip()})",
            "enum": [
                TaskStatus.COMPLETED.value,
                TaskStatus.SUBMITTED.value,
            ],
        }
        for course in courses
        for task in course.tasks
    }

    SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Users Config",
        "type": "object",
        "required": ["users"],
        "properties": {
            "users": {
                "description": "Moodle Users to create.",
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "required": [
                                "name",
                                "capabilities",
                                "token",
                                "class",
                                "task-status",
                            ],
                            "properties": {
                                "task-status": {
                                    "type": "object",
                                    "description": "Map<String, submitted|done>",
                                    "properties": status_props,
                                    "additionalProperties": False,
                                },
                                "class": {
                                    "type": "string",
                                    "enum": [c.value for c in Clazz],
                                },
                                "name": {"type": "string"},
                                "submitted_tasks": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "capabilities": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [c.value for c in Capability],
                                    },
                                },
                                "token": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "required": ["name", "capabilities", "token"],
                            "properties": {
                                "class": {
                                    "type": "string",
                                    "enum": [c.value for c in Clazz],
                                },
                                "name": {"type": "string"},
                                "capabilities": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            c.value
                                            for c in Capability
                                            if c != Capability.STUDENT
                                        ],
                                    },
                                },
                                "token": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                    ]
                },
            }
        },
        "additionalProperties": False,
    }
    print(f"generating schema files to \033[34m{dp}\033[0m")

    fn = "users.yml.schema.json"
    fp = pathjoin(dp, fn)

    with open(fp, "w") as f:
        import json

        json.dump(SCHEMA, f, indent=4)

    print(f"\t\033[32mdone\033[0m: {fn}")
