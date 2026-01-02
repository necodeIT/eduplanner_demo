from abc import ABC, abstractmethod
from contextlib import contextmanager
from collections.abc import Iterator, Collection

from .model import Task as mTask, User as mUser, Course as mCourse

#
# NOTE: MoodleAdapterOpen and MoodleAdapter are normally the same object,
#       this is just structured this way for type checking purposes.
#

class MoodleAdapterOpen(ABC):
	""" adapter to communicate with moodle - opened and ready for communication """
	@abstractmethod
	def clear(self) -> None:
		""" clear everything """
		...

	@abstractmethod
	def add_courses(self, courses: Collection[mCourse]) -> None:
		""" add courses (NOTE: sets moodleID for courses) """
		...
	
	@abstractmethod
	def add_tasks(self, tasks: Collection[tuple[mCourse, mTask]]) -> None:
		""" adds all tasks contained within these courses
		
		NOTE: sets moodleID for tasks
		NOTE: courses must have moodleID set """
		...

	@abstractmethod
	def add_users(self, users: Collection[mUser], token: str) -> None:
		""" add users (NOTE: sets moodleID for users) """
		...

	@abstractmethod
	def add_user_enrols(self, user: mUser, courses: Collection[mCourse]) -> None:
		""" enrol user in courses """
		...

	@abstractmethod
	def add_submissions(self, tasks: Collection[tuple[mUser, mTask]]) -> None:
		""" add user submissions to all listed tasks (NOTE: both user and tasks must have IDs set) """
		...
	
	@abstractmethod
	def add_grades(self, tasks: Collection[tuple[mUser, mTask]]) -> None:
		""" sets full-mark grades for the passed tasks """
		...


class MoodleAdapterClosed(ABC):
	""" adapter to communicate with moodle - closed and dormant """
	@abstractmethod
	@contextmanager
	def connect(self) -> Iterator[MoodleAdapterOpen]:
		""" enables safe cleanup via `with` statement """
		...


class MoodleAdapter(MoodleAdapterClosed, MoodleAdapterOpen):
	...
