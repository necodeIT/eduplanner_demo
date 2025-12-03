from eduplanner_demo.model import Capability, Clazz, TaskStatus
from eduplanner_demo.config import read_courses_config
from os.path import dirname, join as pathjoin

courses = read_courses_config()

tasks = [task.id for course in courses for task in course.tasks]


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

fp = pathjoin(dirname(dirname(__file__)), 'schema/users.yml.schema.json')

with open(fp, "w") as f:
    import json

    json.dump(SCHEMA, f, indent=4)
