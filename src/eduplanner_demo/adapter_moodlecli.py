from os import stat, getuid
from os.path import realpath, join as pathjoin
from pwd import getpwuid
from functools import cached_property
from subprocess import Popen, PIPE, DEVNULL
from enum import StrEnum, auto
from collections.abc import Iterable
from typing import Iterator
from contextlib import contextmanager

from .moodleadapter import MoodleAdapter, MoodleAdapterOpen

class SCRIPTNAME(StrEnum):
	MAINTENANCE = auto()
	PURGE_CACHES = auto()

class MoodleCLI(MoodleAdapter):
	""" Connects to a moodle instance via the CLI scripts """
	__slots__ = ('moodledir')

	moodledir: str
	""" where moodle is located """
	
	def __init__(self, moodledir: str):
		self.moodledir = realpath(moodledir)
	
	@contextmanager
	def connect(self) -> Iterator[MoodleAdapterOpen]:
		if self.exec_uid != getuid():
			raise OSError(f"Must run as f{getpwuid(self.exec_uid).pw_name}, f{getpwuid(getuid()).pw_name} instead")
		
		self.enable_maintenance()
		try:
			yield self
		finally:
			self.disable_maintenance()
	
	def enable_maintenance(self) -> None:
		self.__run_script(SCRIPTNAME.MAINTENANCE, ("--enable",))

	def disable_maintenance(self) -> None:
		self.__run_script(SCRIPTNAME.MAINTENANCE, ("--disable",))
	
	# TODO: implement adapter functions
	
	def __run_script(self, name: SCRIPTNAME, params: Iterable[str], communicate: bool | str = False) -> str | None:
		""" Popens script and passes parameters to it

		:param SCRIPTNAME name: name of the script to execute
		:param Iterable[str] params: parameters to pass to the script
		:param bool|str communicate: whether to communicate with the script - will be passed to stdin if string
		:return str|None: stdout if communicate was true, None otherwise
		"""
		with self.__popen_script(name, params) as p:
			if communicate:
				out = p.communicate(communicate if isinstance(communicate, str) else None)[0].decode('utf-8')
			else:
				out = None
			assert p.wait() == 0 # TODO: proper error handling
		
		return out
	
	def __popen_script(self, name: SCRIPTNAME, params: Iterable[str]) -> Popen:
		""" Popens script and passes parameters to it

		:param SCRIPTNAME name: name of the script to execute
		:param Iterable[str] params: parameters to pass to the script
		:return Popen: the running process
		"""
		return Popen(
			[pathjoin(self.script_folder, f"{name}.php"), *params],
			stdout=PIPE, stderr=DEVNULL
		)
	
	@cached_property
	def exec_uid(self) -> int:
		""" the UID of the user to execute moodle stuff as (meant to be apache, httpd, etc.) """
		return stat(self.lbp_folder).st_uid
	
	@cached_property
	def lbp_folder(self) -> str:
		""" the folder containing Eduplanner """
		return pathjoin(self.moodledir, "local/lbplanner/")
	
	@cached_property
	def script_folder(self) -> str:
		""" the folder containing all the scripts we're using """
		return pathjoin(self.moodledir, "admin/cli/")
