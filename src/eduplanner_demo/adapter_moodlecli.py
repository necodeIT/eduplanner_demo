from os import stat, getuid
from os.path import realpath, join as pathjoin
from pwd import getpwuid
from functools import cached_property
from subprocess import Popen, PIPE, DEVNULL
from enum import StrEnum, auto
from collections.abc import Iterator, Iterable, Collection
from contextlib import contextmanager

from .moodleadapter import MoodleAdapter, MoodleAdapterOpen
from .model import User as mUser, Task as mTask, Course as mCourse

#
# NOTE: All of this essentially works by injecting php code into the moodle codebase (or if you wanna see it that way:
#       importing the entire moodle codebase into some small php scripts) to abuse their internal functions because yup,
#       that is indeed the easiest and most robust way of doing it.
#
# BEGIN TANGENT
#       Maybe a custom plugin would be more "proper" but it would be much more effort, less performant, and exactly as
#       robust - ranging from "not very" to "incredibly", depending on how you view the fact that moodle devs rarely
#       touch their terrible undocumented internal functions.
#       Either way, there might be a way to do it using the backup system, but knowing how fragile that is, I'll try
#       that another time.
# END

class SCRIPTNAME(StrEnum):
	MAINTENANCE = auto()
	PURGE_CACHES = auto()

class DBTable(StrEnum):
	LBP_COURSES = "local_lbplanner_courses"
	LBP_KANBANENTRIES = "local_lbplanner_kanbanentries"
	LBP_NOTIFICATIONS = "local_lbplanner_notification"
	LBP_PLAN_ACCESS = "local_lbplanner_plan_access"
	LBP_PLAN_DEADLINES = "local_lbplanner_deadlines"
	LBP_PLAN_INVITES = "local_lbplanner_plan_invites"
	LBP_PLANS = "local_lbplanner_plans"
	LBP_RESERVATIONS = "local_lbplanner_reservations"
	LBP_SLOTFILTERS = "local_lbplanner_slot_courses"
	LBP_SLOTS = "local_lbplanner_slots"
	LBP_SUPERVISORS = "local_lbplanner_supervisors"
	LBP_USERS = "local_lbplanner_users"
	COURSES = "course"
	USERS = "user"
	SUBMISSIONS = "assign_submission"
	GRADES = "assign_grades"

def e(orig: str) -> str:
	""" escapes strings so they can be used for inserting into php single-quoted strings """
	return orig.replace('\\', '\\\\').replace('\'', "\\'") # should be good enough

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
		""" enables moodle maintenance mode """
		self.__run_script(SCRIPTNAME.MAINTENANCE, ("--enable",))

	def disable_maintenance(self) -> None:
		""" disables moodle maintenance mode """
		self.__run_script(SCRIPTNAME.MAINTENANCE, ("--disable",))
	
	def clear(self) -> None:
		self.__run_code(f"""\
$DB->delete_records("{DBTable.LBP_NOTIFICATIONS}");
$DB->delete_records("{DBTable.LBP_RESERVATIONS}");
$DB->delete_records("{DBTable.LBP_SLOTFILTERS}");
$DB->delete_records("{DBTable.LBP_SLOTS}");
$DB->delete_records("{DBTable.LBP_PLAN_INVITES}");
$DB->delete_records("{DBTable.LBP_PLAN_DEADLINES}");
$DB->delete_records("{DBTable.LBP_PLAN_ACCESS}");
$DB->delete_records("{DBTable.LBP_PLANS}");
$DB->delete_records("{DBTable.LBP_SUPERVISORS}");
$DB->delete_records("{DBTable.LBP_KANBANENTRIES}");
$DB->delete_records("{DBTable.LBP_COURSES}");
$DB->delete_records("{DBTable.LBP_USERS}");

$alluserids = $DB->get_fieldset('{DBTable.USERS}', 'id');
foreach ($alluserids as $userid) {{
	delete_user($DB->get_record('user', ['id' => $userid]));
}}
$allcourseids = $DB->get_fieldset('{DBTable.COURSES}', 'id');
foreach ($allcourseids as $courseid) {{
	delete_course($courseid, false);
}}
""")

	def add_users(self, users: Iterable[mUser]) -> None:
		caplists = {user.name: ",".join([f"'local/lb_planner:{cap}'" for cap in user.capabilities]) for user in users}
		clazzs = {user.name: f"'{e(user.clazz)}'" if user.clazz is not None else 'null' for user in users}
		data = ",".join([f"'{e(user.name)}'=>['{user.token}',[{caplists[user.name]}],{clazzs[user.name]}]" for user in users])
		stdout = self.__run_code(f"""\
$tocreate = [{data}];

$syscontext = context_system::instance(0, MUST_EXIST, false);

foreach ($tocreate as $usrname => [$passwd, $capabilities, $clazz]) {{
	$userid = create_user_record($usrname, $passwd)->id;
	foreach ($capabilities as $capability) {{
		$role = get_roles_with_capability($capability)[0];
		role_assign($role->id, $userid, $syscontext);
	}}
	if ($clazz !== null)
		$DB->set_field('{DBTable.USERS}', 'address', $clazz);
	echo $userid;
}}
""", True)
		assert stdout is not None
		userIDs = stdout.split('\n')
		for user, userID in zip(users, userIDs):
			user.moodleid = int(userID)

	def add_courses(self, courses: Iterable[mCourse]) -> None:
		data = ",".join([
			f"['fullname' => '{e(course.name)}', 'shortname' => '{e(course.name)}', 'category' => $catid, 'idnumber' => '']"
			for course in courses
		])
		stdout = self.__run_code(f"""\
$catid = core_course_category::get_default()->id;
$courses = [
	{data}
];

foreach ($courses as $course) {{
	echo create_course((object)$course)->id;
}}
""", True)
		assert stdout is not None
		courseIDs = stdout.split('\n')
		for course, courseID in zip(courses, courseIDs):
			course.moodleid = int(courseID)

	def add_tasks(self, tasks: Collection[tuple[mCourse, mTask]]) -> None:
		assigns = ",".join([
			f"""[
				'name' => '{e(task.name)}',
				'description' => '{e(task.description)}',
				'duedate' => {task.absdue},
				'courseid' => {course.moodleid}
			]""" for course, task in tasks
		])
		
		stdout = self.__run_code(f"""\
$assigns = [{assigns}];

foreach ($assigns as $assign) {{
	echo assign_add_instance((object)$assign);
}}
""", True)
		assert stdout is not None
		taskIDs = stdout.split('\n')
		assert len(taskIDs) == len(tasks)
		for (course, task), taskID in zip(tasks, taskIDs):
			task.moodleid = int(taskID)

	def add_submissions(self, tasks: Iterable[tuple[mUser, mTask]]) -> None:
		data = ",".join([
			f"['userid' => {user.moodleid}, 'assignment' => {task.moodleid}, 'status' => 'submitted', 'latest' => 1]"
			for user, task in tasks
		])
		self.__run_code(f"""\
$data = [
	{data}
];
$DB->insert_records('{DBTable.SUBMISSIONS}', $data);
""")

	def add_grades(self, tasks: Iterable[tuple[mUser, mTask]]) -> None:
		
		assigns = ",".join([f"[{user.moodleid}, {task.moodleid}]" for user, task in tasks])
		
		self.__run_code(f"""\
$assigns = [
	{assigns}
];

foreach ($assigns as [$userid, $assignid]) {{
	$cm = get_coursemodule_from_instance('assign', $assignid, 0, false, MUST_EXIST);
	$context = context_module::instance($cm->id);
	$assignment = new assign($context, $cm, null);
	$grade = $assignment->get_user_grade($userid, true, 1);
	$grade->grade = '100';
	$assignment->update_grade($grade);
}}
""")

	def __run_code(self, code: str, communicate: bool | str = False) -> str | None:
		""" Popens code and stuff

		:param str code: the php code to execute
		:param bool|str communicate: whether to communicate with the script - will be passed to stdin if string
		:return str|None: stdout if communicate was true, None otherwise
		"""
		out: str | None
		with self.__popen_code(code) as p:
			if communicate:
				out = p.communicate(communicate if isinstance(communicate, str) else None)[0].decode('utf-8')
			else:
				out = None
			assert p.wait() == 0 # TODO: proper error handling
		
		return out

	def __popen_code(self, code: str) -> Popen:
		""" Popens custom php code with moodle context

		:param str code: the php code to execute
		:return Popen: the running process
		"""
		bootstrap = f"""\
define('CLI_SCRIPT', true);
require('${pathjoin(self.moodledir, 'config.php')}');
"""
		return Popen(
			["php", '-r', f"{bootstrap}{code}", '--'],
			stdout=PIPE, stderr=DEVNULL
		)

	def __run_script(self, name: SCRIPTNAME, params: Iterable[str], communicate: bool | str = False) -> str | None:
		""" Popens script and passes parameters to it

		:param SCRIPTNAME name: name of the script to execute
		:param Iterable[str] params: parameters to pass to the script
		:param bool|str communicate: whether to communicate with the script - will be passed to stdin if string
		:return str|None: stdout if communicate was true, None otherwise
		"""
		out: str | None
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
			["php", '-f', pathjoin(self.script_folder, f"{name}.php"), '--', *params],
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
