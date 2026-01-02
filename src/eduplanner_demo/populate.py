from .model import Task, TaskStatus, User
from .config import Config
from .moodleadapter import MoodleAdapterClosed

def populate(adapter: MoodleAdapterClosed, config: Config) -> None:
	""" resets moodle in terms of what eduplanner cares about """
	with adapter.connect() as mdl:
		mdl.clear()

		passwd, users, courses, slots, plans = config.read_moodle_config()
		tasks = [(course, task) for course in courses for task in course.tasks]
		course_bytaskname = {task.id: course for course, task in tasks}
		tasks_bytaskname = {task[1].id: task[1] for task in tasks}
		courses_byusername = {user.name: [course_bytaskname[taskname] for taskname in user.task_status.keys()] for user in users}
		
		mdl.add_courses(courses)
		mdl.add_tasks(tasks)
		mdl.add_users(users, passwd)
		# TODO: slots
		# TODO: plans
		
		submissions2add: list[tuple[User, Task]] = []
		completions2add: list[tuple[User, Task]] = []
		for user in users:
			courses = courses_byusername[user.name]
			mdl.add_user_enrols(user, courses)
			
			for name, status in user.task_status.items():
				task = tasks_bytaskname[name]
				if status in (TaskStatus.SUBMITTED, TaskStatus.COMPLETED):
					submissions2add.append((user, task))
				if status == TaskStatus.COMPLETED:
					completions2add.append((user, task))
			
		mdl.add_submissions(submissions2add)
		mdl.add_grades(completions2add)
