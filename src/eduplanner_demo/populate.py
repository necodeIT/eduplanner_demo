from .model import Capability, Clazz, Course, Task, TaskStatus, User
from .config import Config
from .moodleadapter import MoodleAdapterClosed

def populate(adapter: MoodleAdapterClosed, config: Config) -> None:
	""" resets moodle in terms of what eduplanner cares about """
	with adapter.connect() as mdl:
		mdl.clear()

		users, courses = config.read_moodle_config()
		
		mdl.add_courses(courses)
		# TODO: set tasks
		# TODO: set users and their accompanying data
