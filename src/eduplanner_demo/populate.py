from .model import Capability, Clazz, Course, Task, TaskStatus, User
from .config import Config
from .moodleadapter import MoodleAdapterClosed

def populate(adapter: MoodleAdapterClosed, config: Config) -> None:
	""" resets moodle in terms of what eduplanner cares about """
	with adapter.connect() as mdl:
		# TODO: mdl.clear_submissions()
		# TODO: mdl.clear_tasks()
		# TODO: mdl.clear_plans()
		# TODO: mdl.clear_courses()
		mdl.clear_users()

		# TODO: set courses and their accompanying data
		# TODO: set users and their accompanying data
