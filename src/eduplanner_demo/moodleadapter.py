from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

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
	def add_courses(self, courses: list[mCourse]) -> None:
		""" add courses (NOTE: sets moodleID for courses) """
		...

	@abstractmethod
	def add_submissions(self, tasks: list[mTask], user: mUser) -> None:
		""" add user submissions to all listed tasks (NOTE: both user and tasks must have IDs set) """
		...

	@abstractmethod
	def add_users(self, users: list[mUser]) -> None:
		""" add users (NOTE: sets moodleID for users) """
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
