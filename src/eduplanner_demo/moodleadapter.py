from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

from .model import Task as mTask, User as mUser

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
	def set_submissions(self, tasks: list[mTask], user: mUser) -> None:
		""" add user submissions to all listed tasks """
		...

	@abstractmethod
	def add_users(self, users: list[mUser]) -> None:
		""" add users """
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
