#!/bin/python3
import yaml
from model import Task, Course, User, Capability, Clazz, TaskStatus, toId


def read_users_config(tasks: list[Task]) -> list[User]:
    with open("users.yml") as f:
        config = yaml.safe_load(f)

    users = []
    for user_data in config["users"]:
        capabilities = [Capability(cap) for cap in user_data.get("capabilities", [])]
        clazz = (
            Clazz(user_data["class"])
            if "class" in user_data and user_data["class"] is not None
            else None
        )
        task_status = {}
        for task_id, status in user_data.get("task-status", {}).items():

            task = next((task for task in tasks if task.id == toId(task_id)), None)
            if task is not None:
                task_status[task] = TaskStatus(status)

        user = User(
            name=user_data["name"],
            capabilities=capabilities,
            clazz=clazz,
            token=user_data["token"],
            task_status=task_status,
        )
        users.append(user)
    return users


def read_courses_config() -> list[Course]:

    with open("courses.yml") as f:
        config = yaml.safe_load(f)
    courses = []
    for course_data in config["courses"]:
        tasks = []
        for task_data in course_data.get("tasks", []):
            task = Task(
                name=task_data["name"],
                parent=course_data["name"],
                due=task_data["due"],
                description=task_data.get("description", ""),
            )
            tasks.append(task)
        course = Course(name=course_data["name"], tasks=tasks)
        courses.append(course)
    return courses


def read_moodle_config() -> tuple[list[User], list[Course]]:

    courses = read_courses_config()

    return (
        read_users_config([task for course in courses for task in course.tasks]),
        courses,
    )


if __name__ == "__main__":
    users, courses = read_moodle_config()
    for user in users:
        print(
            f"User: {user.name}, Capabilities: {[cap.value for cap in user.capabilities]}, Class: {user.clazz.value if user.clazz else 'N/A'}, Task Status: { {task.id: status.value for task, status in user.task_status.items()} }"
        )
    for course in courses:
        print(f"Course: {course.name}")
        for task in course.tasks:
            print(
                f"  Task: {task.name}, Due in: {task.due} days, Description: {task.description.strip()}, ID: {task.id}"
            )
