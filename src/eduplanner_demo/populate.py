from .logger import Logger
from .model import Task, TaskStatus, User
from .config import Config
from .moodleadapter import MoodleAdapterClosed

def populate(adapter: MoodleAdapterClosed, config: Config) -> None:
	""" resets moodle in terms of what eduplanner cares about """
	with adapter.connect() as mdl:
		Logger.info("Clearing Moodle data...")

		mdl.clear()

		passwd, users, courses, slots, plans = config.read_moodle_config()
		tasks = [(course, task) for course in courses for task in course.tasks]
		course_bytaskname = {task.id: course for course, task in tasks}
		tasks_bytaskname = {task[1].id: task[1] for task in tasks}
		courses_byusername = {user.name: [course_bytaskname[taskname] for taskname in user.task_status.keys()] for user in users}
		
		Logger.success("Cleared Moodle data.")
  
		Logger.info("Populating Moodle data...")
  
		mdl.add_courses(courses)
		Logger.success("Added courses.")
  
		mdl.add_tasks(tasks)
		Logger.success("Added tasks.")

		mdl.add_users(users, passwd)
		Logger.success("Added users.")		
  
  
		submissions2add: list[tuple[User, Task]] = []
		completions2add: list[tuple[User, Task]] = []
		for user in users:
			courses = courses_byusername[user.name]
			mdl.add_user_enrols(user, courses)
			Logger.debug(f"Enrolled user {user.name} in courses {[c.id for c in courses]}")
			
			for name, status in user.task_status.items():
				task = tasks_bytaskname[name]
				if status in (TaskStatus.SUBMITTED, TaskStatus.COMPLETED):
					submissions2add.append((user, task))
				if status == TaskStatus.COMPLETED:
					completions2add.append((user, task))
			
		mdl.add_submissions(submissions2add)
		Logger.success("Added submissions.")
		mdl.add_grades(completions2add)
		Logger.success("Added grades.")
		mdl.add_plans(plans)
		Logger.success("Added plans.")
		mdl.add_slots(slots)
		Logger.success("Created slots.")
