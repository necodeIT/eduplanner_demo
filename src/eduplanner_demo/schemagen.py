from .logger import Logger
from .model import Capability, Clazz, Course, TaskStatus, User, Weekday
from .config import Config
from os.path import join as pathjoin

config = Config()

courses = config.read_courses_config()


def schemagen(dp: str, courses: list[Course], users: list[User]) -> None:
    """Generates schema files to a folder

    :param list[Course] courses: existing courses to take into account
    :param str dp: directory path to save schema files to
    """
    
    Logger.info(f"generating schema files to {dp}...")


    Logger.debug("Generating user schema...")

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

    plan_props = {
        task.id: {
            "type": "object",
            "description": task.description.strip(),
            "title": f"{task.name} ({course.name.strip()})",
            "properties": {
                "start": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "number of days from today when the task is planned to be started",
                },
                "end": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "number of days from today when the task is planned to be due",
                },
            },
        }
        for course in courses
        for task in course.tasks
    }

    USER_SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Users Config",
        "type": "object",
        "required": ["users", "password"],
        "properties": {
            "password": {
                "type": "string",
                "description": "Default password for created users.",
            },
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
                            },
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "required": ["name", "capabilities"],
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
                            },
                            "additionalProperties": False,
                        },
                    ]
                },
            }
        },
        "additionalProperties": False,
    }

    fn = "users.yml.schema.json"
    fp = pathjoin(dp, fn)

    with open(fp, "w") as f:
        import json

        json.dump(USER_SCHEMA, f, indent=4)
        
    Logger.success(fn)

    Logger.debug("Generating slots schema...")

    SLOTS_SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Slots Config",
        "type": "object",
        "required": ["slots"],
        "properties": {
            "slots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "weekday",
                        "start",
                        "duration",
                        "supervisors",
                        "room",
                        "capacity",
                        "mappings",
                        "disambiguate",
                    ],
                    "properties": {
                        "disambiguate": {"type": "integer", "minimum": 0},
                        "weekday": {
                            "enum": [
                                w.name.lower() for w in Weekday
                            ]
                        },
                        "start_hour": {"type": "integer", "minimum": 1, "maximum": 16},
                        "duration": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 16,
                        },
                        "supervisors": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    u.id
                                    for u in users
                                    if Capability.TEACHER in u.capabilities
                                ],
                            },
                        },
                        "room": {"type": "string", "maxLength": 7},
                        "capacity": {"type": "integer", "minimum": 1},
                        "mappings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["class", "course"],
                                "properties": {
                                    "class": {
                                        "type": "string",
                                        "enum": [c.value for c in Clazz],
                                    },
                                    "course": {
                                        "type": "string",
                                        "enum": [c.id for c in courses],
                                    },
                                },
                            },
                        },
                    },
                },
                "additionalProperties": False,
            }
        },
    }
    
    fn = "slots.yml.schema.json"
    fp = pathjoin(dp, fn)
    with open(fp, "w") as f:
        import json

        json.dump(SLOTS_SCHEMA, f, indent=4)

    Logger.success(fn)

    Logger.debug("Generating plans schema...")

    PLANS_SCHEMA = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EduPlanner Demo Plans Config",
        "type": "object",
        "required": ["plans"],
        "properties": {
            "plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "deadlines", "owner"],
                    "properties": {
                        "name": {"type": "string"},
                        "owner": {
                            "description": "The owner of the plan.",
                            "type": "string",
                            "enum": [
                                user.id
                                for user in users
                                if Capability.STUDENT in user.capabilities
                            ],
                        },
                        "members": {
                            "type": "array",
                            "description": "Users the plan is shared with (write access)",
                            "items": {
                                "type": "string",
                                "enum": [
                                    user.id
                                    for user in users
                                    if Capability.STUDENT in user.capabilities
                                ],
                            },
                        },
                        "deadlines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["task", "deadlinestart"],
                                "properties": {
                                    "task": {
                                        "type": "string",
                                        "enum": [
                                            task.id
                                            for course in courses
                                            for task in course.tasks
                                        ],
                                    },
                                    "deadlinestart": {
                                        "type": "integer",
                                        "description": "Days after now when the deadline starts.",
                                        "minimum": 0,
                                    },
                                    "duration": {
                                        "type": "integer",
                                        "description": "Days after deadline start when the deadline ends.",
                                        "minimum": 0,
                                    },
                                },
                            },
                        },
                    },
                },
            }
        },
    }




    fn = "plans.yml.schema.json"
    fp = pathjoin(dp, fn)
    with open(fp, "w") as f:
        import json

        json.dump(PLANS_SCHEMA, f, indent=4)

    Logger.success(fn)
  

  
    
