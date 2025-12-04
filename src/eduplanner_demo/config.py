from os.path import exists, isdir, expanduser, realpath, join as pathjoin
import yaml
import eduplanner_demo
from eduplanner_demo.model import Task, Course, User, Capability, Clazz, TaskStatus, toId


class Config:
    __configdir: str
    """the directory with config files inside"""

    def __init__(self, configdir: str | None = None):
        if configdir is None:
            configdir = self.find_configdir()
        else:
            configdir = realpath(configdir)
            if not exists(configdir):
                raise IOError(f"{configdir} does not exist")
            elif not isdir(configdir):
                raise IOError(f"{configdir} is not a directory")

        self.__configdir = configdir

    def get_config(self, name: str) -> str:
        """Tries to return a config file matching the requested name

        :param str name: name of the config file to get (without path nor file extension)
        :raises: :class:`FileNotFoundError`: could not find config file
        :return str: the config file path
        """
        fp = pathjoin(self.__configdir, f"{name}.yml")
        if not exists(fp):
            raise FileNotFoundError(f"could not find config file \"{fp}\"")
        return fp

    @classmethod
    def find_configdir(cls) -> str:
        """Tries to find a directory to read configs from.

        :raises: :class:`IOError`: no config found
        :return str: the found directory
        """
        # TODO: cross-platform solution
        candidates = (
            realpath(pathjoin(eduplanner_demo.__file__, '../../../config')), # for config in project root
            expanduser('~/.config/eduplanner_demo'),
            '/etc/eduplanner_demo'
        )
        for folder in candidates:
            if exists(folder):
                return folder

        raise OSError('no config folder found')

    def read_users_config(self, tasks: list[Task]) -> list[User]:
        """Reads the users configuration from the YAML file and creates User objects.

        :param list[Task] tasks: A list of Task objects used to resolve task IDs in user
                            task-status configurations.
        :return list[User]: A list of User objects created from the configuration file, each
                    containing name, capabilities, class, token, and task status mappings.
        """
        with open(self.get_config('users')) as f:
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

    def read_courses_config(self) -> list[Course]:
        """
        Read and parse course configuration from a YAML file.

        Loads course data from 'config/courses.yml' and converts it into a list of Course objects.
        Each course can contain multiple tasks with their respective properties.

        :return list[Course]: A list of Course objects, each containing their associated tasks.
        """

        with open(self.get_config('courses')) as f:
            config = yaml.safe_load(f)
        courses = []
        for course_data in config["courses"]:
            tasks = []
            for task_data in course_data.get("tasks", []):
                task = Task(
                    name=task_data["name"],
                    parent=toId(course_data["name"]),
                    due=task_data["due"],
                    description=task_data.get("description", ""),
                )
                tasks.append(task)
            course = Course(name=course_data["name"], tasks=tasks)
            courses.append(course)
        return courses

    def read_moodle_config(self) -> tuple[list[User], list[Course]]:
        """Reads the Moodle configuration including users and courses.

        :return tuple[list[User], list[Course]]: A tuple containing a list of User objects and a list of Course objects.
        """

        courses = self.read_courses_config()

        return (
            self.read_users_config([task for course in courses for task in course.tasks]),
            courses,
        )


def print_config(config: Config):
    users, courses = config.read_moodle_config()
    print("Users:")
    for user in users:
        print(
            f"""\
|\t{user.name}
|\t|\tCapabilities: {[cap.value for cap in user.capabilities]}
|\t|\tClass: {user.clazz.value if user.clazz else 'N/A'}
|\t|\tTasks:"""
        )
        for task, status in user.task_status.items():
            print(f"|\t|\t|\t{task.id}: '{status}'")
    print("Courses:")
    for course in courses:
        print(f"|\t{course.name}")
        print("|\t|\tTasks:")
        for task in course.tasks:
            print(
                f"""\
|\t|\t|\t{task.name} \033[2m({task.id})\033[0m
|\t|\t|\t|\tDue in: {task.due} days
|\t|\t|\t|\tDescription: {task.description.strip()}"""
            )
