from os.path import exists, isdir, expanduser, realpath, join as pathjoin
import yaml
import eduplanner_demo
from eduplanner_demo.model import Plan, Deadline, Slot, SlotMapping, Task, Course, User, Capability, Clazz, TaskStatus, Weekday, find_course, toId, find_user, find_task



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

    def read_users_config(self, tasks: list[Task]) -> tuple[list[User], str]:
        """Reads the users configuration from the YAML file and creates User objects.

        :param list[Task] tasks: A list of Task objects used to resolve task IDs in user
                            task-status configurations.
        :return list[User]: A list of User objects created from the configuration file, each
                    containing name, capabilities, class, token, and task status mappings.
        """
        with open(self.get_config('users')) as f:
            config = yaml.safe_load(f)

        if config is None:
            return ([], "")
        users = []
        for user_data in config.get("users", []):
            capabilities = [Capability(cap) for cap in user_data.get("capabilities", [])]
            clazz = (
                Clazz(user_data["class"])
                if "class" in user_data and user_data["class"] is not None
                else None
            )
            task_status: dict[str, TaskStatus] = {}
            for task_id, status in user_data.get("task-status", {}).items():
                task_status[find_task(tasks, task_id).id] = TaskStatus(status)
                
            user = User(
                name=user_data["name"],
                capabilities=capabilities,
                clazz=clazz,
                task_status=task_status,
            )
            users.append(user)
            
        
        return  (users, config.get("password", "default-password123"))
    
    def read_slots_config(self, users: list[User], courses: list[Course]) -> list[Slot]:
        """Reads and parses slot configuration from a YAML file.

        Loads slot data from 'config/slots.yml' and converts it into a list of Slot objects.
        Each slot can contain multiple mappings with their respective properties.

        :return list[Slot]: A list of Slot objects, each containing their associated mappings.
        """

        with open(self.get_config('slots')) as f:
            config = yaml.safe_load(f)
            
        if config is None:
            return []
        slots = []
        for slot_data in config.get("slots", []):
            mappings = [
                 SlotMapping(
                    clazz=Clazz(mapping_data["class"]),
                    course=find_course(courses, mapping_data["course"]),
                ) for mapping_data in slot_data.get("mappings", [])
            ]
            
            supervisors = []
            for supervisor_id in slot_data.get("supervisors", []):
                supervisor = find_user(users, supervisor_id)
                if Capability.TEACHER not in supervisor.capabilities:
                    raise ValueError(f"supervisor '{supervisor_id}' does not have TEACHER capability")
                supervisors.append(supervisor)
                
            startunit = slot_data.get("startunit", 1)
            duration = slot_data.get("duration", 1)
            if startunit + duration > 16:
                raise ValueError(f"slot starting at unit {startunit} with duration {duration} exceeds maximum unit 16")
            
            room = slot_data.get("room", "")
            capacity = slot_data.get("capacity", 0)
            if len(room) > 7:
                raise ValueError(f"room '{room}' exceeds maximum length of 7 characters")
                
            slot = Slot(
                supervisors=supervisors,
                disambiguate=slot_data["disambiguate"],
                startunit=startunit,
                duration=duration,
                weekday=Weekday[slot_data["weekday"].upper()],
                room=room,
                capacity=capacity,
                mappings=mappings,
            )
            slots.append(slot)
            
        return slots

    def read_courses_config(self) -> list[Course]:
        """
        Read and parse course configuration from a YAML file.

        Loads course data from 'config/courses.yml' and converts it into a list of Course objects.
        Each course can contain multiple tasks with their respective properties.

        :return list[Course]: A list of Course objects, each containing their associated tasks.
        """

        with open(self.get_config('courses')) as f:
            config = yaml.safe_load(f)
            
        if config is None:
            return []
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
    
    def read_plans_config(self, users: list[User], tasks: list[Task]) -> list[Plan]:
        """Reads and parses plan configuration from a YAML file.

        Loads plan data from 'config/plans.yml' and converts it into a list of Plan objects.
        Each plan can contain multiple deadlines with their respective properties.

        :return list[Plan]: A list of Plan objects, each containing their associated deadlines.
        """

        with open(self.get_config('plans')) as f:
            config = yaml.safe_load(f)
            
        if config is None:
            return []
        
        plans = []
        for plan_data in config["plans"]:
            deadlines = [
                Deadline(
                    find_task(tasks, deadline_data["task"]),
                    deadline_data["deadlinestart"],
                    deadline_data.get("duration", 0),
                )
                for deadline_data in plan_data["deadlines"]
            ]
                
            owner = find_user(users, plan_data["owner"])
            assert Capability.STUDENT in owner.capabilities
            members = [find_user(users, member_id) for member_id in plan_data.get("members", [])]
            assert all(Capability.STUDENT in member.capabilities for member in members)
            
            plans.append(Plan(plan_data["name"], deadlines, owner, members))
        
        return plans

    def read_moodle_config(self) -> tuple[str, list[User], list[Course], list[Slot], list[Plan]]:
        """Reads the Moodle configuration including users and courses.

        :return tuple[list[User], list[Course], list[Slot]]: A tuple containing everything read from the config files.
        """

        courses = self.read_courses_config()
        tasks = [task for course in courses for task in course.tasks]
        (users, password) = self.read_users_config(tasks)
        slots = self.read_slots_config(users, courses)
        plans = self.read_plans_config(users, tasks)

        return (
            password,
            users,
            courses,
            slots,
            plans,
        )

def print_config(config: Config):
    password, users, courses, slots, plans = config.read_moodle_config()
    print(f"Users \033[2m(password: {password})\033[0m:")
    for user in users:
        capstring =  "\n".join([f"|\t|\t|\t{cap}" for cap in user.capabilities])

        print(
            f"""\
|\t{user.name}
|\t|\tCapabilities:
{capstring}
|\t|\tClass: {user.clazz.value if user.clazz else 'N/A'}
|\t|\tTasks:"""
        )
        for task_id, status in user.task_status.items():
            print(f"|\t|\t|\t{task_id}: '{status}'")

    print("\nCourses:")
    for course in courses:
        print(f"|\t{course.name}")
        print("|\t|\tTasks:", "" if len(course.tasks) > 0 else "N/A")
        for task in course.tasks:
            print(
                f"""\
|\t|\t|\t{task.name} \033[2m({task.id})\033[0m
|\t|\t|\t|\tDue in: {task.due} days
|\t|\t|\t|\tDescription: {task.description.strip()}"""
            )

    print("\nSlots:")
    for slot in slots:
        print(f"|\t{slot.id}")
        print(
            f"""\
|\t|\tStartunit: {slot.startunit}
|\t|\tDuration: {slot.duration}
|\t|\tWeekday: {slot.weekday.name.lower()}
|\t|\tRoom: {slot.room}
|\t|\tCapacity: {slot.capacity}
|\t|\tMappings:"""
        )
        for mapping in slot.mappings:
            print(f"|\t|\t|\t{mapping.clazz}:{mapping.course.name}")
        print(f"|\t|\tSupervisors:")
        for supervisor in slot.supervisors:
            print(f"|\t|\t|\t{supervisor.name} \033[2m({supervisor.id})\033[0m")
    print("Plans:")
    for plan in plans:
        print(f"|\t{plan.name}")
        print(f"|\t|\tOwner: {plan.owner.name} \033[2m({plan.owner.id})\033[0m")
        print("|\t|\tDeadlines:")
        for deadline in plan.deadlines:
            print(f"""\
|\t|\t|\t{deadline.task.name} \033[2m({deadline.task.id})\033[0m
|\t|\t|\t|\tStart: {deadline.deadlinestart} days
|\t|\t|\t|\tEnd: {deadline.duration} days"""
            )
        print("|\t|\tMembers:")
        for member in plan.members:
            print(f"|\t|\t|\t{member.name} \033[2m({member.id})\033[0m")
        
