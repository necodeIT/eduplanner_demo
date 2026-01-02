from os import stat, getuid
from os.path import realpath, join as pathjoin
from pwd import getpwuid
from functools import cached_property
from subprocess import Popen, PIPE
import json
from enum import StrEnum, auto
from collections.abc import Iterator, Iterable, Collection
from contextlib import contextmanager
from typing import Any
from datetime import datetime, UTC, timedelta
from unittest import result

from .logger import Logger
from .moodleadapter import MoodleAdapter, MoodleAdapterOpen
from .model import Plan, Slot, User as mUser, Task as mTask, Course as mCourse

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
	return orig.replace('\\', '\\\\').replace('\'', "\\'").strip() # should be good enough

def php_serialize(orig: dict | list | str) -> str:
	""" serializes a string into php code """
	if isinstance(orig, dict):
		return '[' + ', '.join([f"{php_serialize(k)}=>{php_serialize(v)}" for k, v in orig.items()]) + ']'
	elif isinstance(orig, list):
		return '[' + ", ".join([php_serialize(v) for v in orig]) + ']'
	elif isinstance(orig, str):
		return f"'{e(orig)}'"
	elif isinstance(orig, int) or isinstance(orig, float):
		return f"{orig}"
	else:
		raise NotImplementedError(f"cannot serialize object of type {type(orig)}")

def php_dump(code: str) -> None:
	""" dumps php code output for debugging purposes """
	
	## print with line numbers in different color


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
			raise OSError(f"Must run as {getpwuid(self.exec_uid).pw_name}, {getpwuid(getuid()).pw_name} instead")
		
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
		self.__run_code(f"""
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
	if ($userid == 1 || $userid == 2) {{
		continue;
	}}
	
	// sometimes during testing the user table will corrupt. this will safely leak memory in that case.
	try {{
		delete_user($DB->get_record('user', ['id' => $userid]));
	}} catch (dml_missing_record_exception) {{
		$DB->delete_records('{DBTable.USERS}', ['id' => $userid]);
	}}
}}
$allcourseids = $DB->get_fieldset('{DBTable.COURSES}', 'id');
foreach ($allcourseids as $courseid) {{
	delete_course($courseid, false);
}}
""")

	def add_users(self, users: Iterable[mUser], token: str) -> None:
		caplists = {user.name: ",".join([f"'local/lb_planner:{cap}'" for cap in user.capabilities]) for user in users}
		clazzs = {user.name: f"'{e(user.clazz)}'" if user.clazz is not None else 'null' for user in users}
		firstnames = {}
		lastnames = {}
		
		for user in users:
			splitpoint = user.name.rfind(' ')
			
			if splitpoint == -1:
				firstnames[user.name] = user.name
				lastnames[user.name] = ''
				continue
			
			firstnames[user.name] = user.name[:splitpoint]
			lastnames[user.name] = user.name[splitpoint + 1:]
		
		data = ",".join([
			f"'{e(user.name.replace(' ', '_'))}'=>"
			f"['{token}',[{caplists[user.name]}],{clazzs[user.name]},'{e(firstnames[user.name])}','{e(lastnames[user.name])}']"
			for user in users
		])
		stdout = self.__run_code(f"""
$tocreate = [{data}];

$syscontext = context_system::instance(0, MUST_EXIST, false);

foreach ($tocreate as $usrname => [$passwd, $capabilities, $clazz, $firstname, $lastname]) {{
	$userid = create_user_record($usrname, $passwd)->id;
	foreach ($capabilities as $capability) {{
		$roles = get_roles_with_capability($capability);
		role_assign(array_key_first($roles), $userid, $syscontext);
	}}
	if ($clazz !== null)
		$DB->set_field('user', 'address', $clazz, ['id' => $userid]);
	$DB->set_field('user', 'firstname', $firstname, ['id' => $userid]);
	$DB->set_field('user', 'lastname', $lastname, ['id' => $userid]);
	$DB->set_field('user', 'email', "user{{$userid}}@example.com", ['id' => $userid]);
	echo $userid . "\\0";
}}
""", True)
		assert stdout is not None
		userIDs = stdout[:-1].split('\0')
		for user, userID in zip(users, userIDs):
			user.moodleid = int(userID)
			# get eduplanner user - this creates it for future use
			self.__run_webservice_function("user_get_user", {}, as_user=user.moodleid)


	def add_courses(self, courses: Collection[mCourse]) -> None:
		data = ",".join([
			f"['fullname' => '{e(course.name)}', 'shortname' => '{e(course.name)}', 'category' => $catid, 'idnumber' => '', 'tags' => ['eduplanner']]"
			for course in courses
		])
		stdout = self.__run_code(f"""
$catid = core_course_category::get_default()->id;
$courses = [
	{data}
];

foreach ($courses as $course) {{
	echo create_course((object)$course)->id . "\\0";
}}
""", True, ['course/lib'])
		assert stdout is not None
		courseIDs = stdout[:-1].split('\0')[:]
		assert len(courseIDs) == len(courses)
		for course, courseID in zip(courses, courseIDs):
			Logger.success(f"Created course '{course.name}' with ID {courseID}")
			course.moodleid = int(courseID)

	def add_user_enrols(self, user: mUser, courses: Collection[mCourse]) -> None:
		data = ",".join([f"{course.moodleid}" for course in courses])
		
		self.__run_code(f"""
$courses = [{data}];
$userid = {user.moodleid};

$studentrole = $DB->get_record('role', ['archetype'=>'student']);
$enrolplugin = enrol_get_plugin('manual');

foreach ($courses as $courseid) {{
	$instance = $DB->get_record('enrol', ['courseid' => $courseid, 'enrol' => 'manual']);
	$enrolplugin->enrol_user($instance, $userid, $studentrole->id);
}}
""")

	def add_tasks(self, tasks: Collection[tuple[mCourse, mTask]]) -> None:
		assigns = ",".join([
			f"""[
				'name' => '{e(task.name)}',
				'description' => '{e(task.description)}',
				'duedate' => {task.absdue},
				'courseid' => {course.moodleid},
				'modulename' => 'assign'
			]""" for course, task in tasks
		])
		
		stdout = self.__run_code(f"""
$assigns = [{assigns}];

$USER->id = 2;

foreach ($assigns as $assign) {{
	$course = get_course($assign['courseid']);
	[$module, $context, $cw, $cm, $data] = prepare_new_moduleinfo_data($course, 'assign', 1);
	$data->name = $assign['name'];
	$data->description = $assign['description'];
	$data->gradingduedate = $data->cutoffdate = $data->duedate = $assign['duedate'];
	// setting bullshit needed by some internal function that has zero effect but we need to set it anyway because ????
	$data->submissiondrafts
		= $data->requiresubmissionstatement
		= $data->sendnotifications
		= $data->sendlatenotifications
		= $data->allowsubmissionsfromdate
		= $data->teamsubmission
		= $data->requireallteammemberssubmit
		= $data->blindmarking
		= $data->markingworkflow
		= $data->markingallocation
		= false;
	$data->grade = 100;
	// setting module and returning assignid
	echo add_moduleinfo($data, $course)->instance . "\\0";
}}
""", True, ["course/modlib", "lib/datalib"])
		assert stdout is not None
		taskIDs = stdout[:-1].split('\0')
		assert len(taskIDs) == len(tasks)
		for (course, task), taskID in zip(tasks, taskIDs):
			task.moodleid = int(taskID)
			Logger.debug(f"Created task '{task.name}' in course '{course.name}' with ID {taskID}")

	def add_submissions(self, tasks: Iterable[tuple[mUser, mTask]]) -> None:
		data = ",".join([
			f"['userid' => {user.moodleid}, 'assignment' => {task.moodleid}, 'status' => 'submitted', 'latest' => 1]"
			for user, task in tasks
		])
		self.__run_code(f"""
$data = [
	{data}
];
$DB->insert_records('{DBTable.SUBMISSIONS}', $data);
""")

	def add_grades(self, tasks: Iterable[tuple[mUser, mTask]]) -> None:
		
		assigns = ",".join([f"[{user.moodleid}, {task.moodleid}]" for user, task in tasks])
		
		self.__run_code(f"""
$assigns = [
	{assigns}
];

foreach ($assigns as [$userid, $assignid]) {{
	$cm = get_coursemodule_from_instance('assign', $assignid, 0, false, MUST_EXIST);
	$context = context_module::instance($cm->id);
	$assignment = new assign($context, $cm, null);
	$grade = $assignment->get_user_grade($userid, true, 1);
	$grade->grade = 100;
	$assignment->update_grade($grade);
}}
""", imports=["mod/assign/locallib"])
  
	def add_plans(self, plans: Collection[Plan]) -> None:
		for plan in plans:
			Logger.debug(f"Creating plan '{plan.name}' owned by user ID {plan.owner.moodleid} with members {[m.moodleid for m in plan.members]}")
			self.__create_plan(plan)
			Logger.debug(f"Created plan '{plan.name}' for owner ID {plan.owner.moodleid}")

	def add_slots(self, slots: Collection[Slot]) -> None:
		for slot in slots:
			Logger.debug(f"Creating slot starting at unit {slot.startunit} on weekday {slot.weekday} in room '{slot.room}' with capacity {slot.capacity}")
			self.__create_slot(slot)
			Logger.debug(f"Created slot ID {slot.moodleid} starting at unit {slot.startunit} on weekday {slot.weekday}")
	

	def __create_slot(self, slot: Slot) -> None:
		""" creates a slot in moodle """
		# create slot 
		result = self.__run_webservice_function("slots_create_slot", {
			"startunit": slot.startunit,
			"duration": slot.duration,
			"weekday": slot.weekday,
			"room": slot.room,
			"size": slot.capacity,
		})
		slot.moodleid = result['id']
		
		# add mappings
		Logger.debug("Adding slot mappings...")
		for mapping in slot.mappings:
			result = self.__run_webservice_function("slots_add_slot_filter", {
				"slotid": slot.moodleid,
				"courseid": mapping.course.moodleid,
				"vintage": mapping.clazz.value,
			})
			mapping.moodleid = result['id']
			Logger.debug(f"Added mapping {mapping.moodleid} to slot {slot.moodleid}")

		
		# add supervisors
		Logger.debug("Adding slot supervisors...")
		for supervisor in slot.supervisors:
			self.__run_webservice_function("slots_add_slot_supervisor", {
				"slotid": slot.moodleid,
				"userid": supervisor.moodleid,
			})
			Logger.debug(f"Added supervisor {supervisor.moodleid} to slot {slot.moodleid}")
  
	def __create_plan(self, plan: Plan) -> None:
		""" creates a plan in moodle """

		invites = {}
	
		# send invites as plan owner to members
		Logger.debug("Inviting plan members...")
		for member in plan.members:
			
			result =  self.__run_webservice_function("plan_invite_user", {
				"inviteeid": member.moodleid
			}, as_user=plan.owner.moodleid)
			invites[member.moodleid] = result['id']
			Logger.debug(f"Invited member {member.moodleid} with invite ID {result['id']}")
		
		# accept invites as members
		Logger.debug("Accepting plan invites...")
		for user_id, invite_id in invites.items():
			self.__run_webservice_function("plan_accept_invite", {
				"inviteid": invite_id
			}, as_user=user_id)
			Logger.debug(f"User {user_id} accepted invite ID {invite_id}")
      
		# set member access to write
		Logger.debug("Setting plan member access...")
		for member in plan.members:
			self.__run_webservice_function("plan_update_access", {
				"accesstype": 1,
				"memberid": member.moodleid
			}, as_user=plan.owner.moodleid)
			Logger.debug(f"Set member {member.moodleid} access to write")
	
	
		# rename plan to plan.name
		Logger.debug("Renaming plan...")
		self.__run_webservice_function("plan_update_plan", {
      		"planname": plan.name,
      	}, as_user=plan.owner.moodleid)
		Logger.debug(f"Renamed plan to '{plan.name}'")
		
  
		now = datetime.now(UTC)


  
		# add deadlines to owner's plan
		Logger.debug("Adding plan deadlines...")
		for deadline in plan.deadlines:
			# UTC+0 unix timestamp from start/end
			start = now + timedelta(days=deadline.deadlinestart)
			end = start + timedelta(days=deadline.duration)
			self.__run_webservice_function("plan_set_deadline", {
				"moduleid": deadline.task.moodleid,
				"deadlinestart": int(start.timestamp()),
				"deadlineend": int(end.timestamp()),
			}, as_user=plan.owner.moodleid)
			Logger.debug(f"Added deadline for task {deadline.task.moodleid} from {start.isoformat()} to {end.isoformat()}")


	def __run_code(self, code: str, communicate: bool | str = False, imports: Iterable[str] = []) -> str | None:
		""" Popens code and stuff

		:param str code: the php code to execute
		:param bool|str: communicate: whether to communicate with the script - will be passed to stdin if string
		:return str|None: stdout if communicate was true, None otherwise
		"""
		out: bytes | None = None
		err: bytes | None = None
		_p, finalcode = self.__popen_code(code, imports)
		with _p as p:
			if communicate:
				out, err = p.communicate(communicate if isinstance(communicate, str) else None)
			
			if p.wait() != 0:
				if not communicate:
					assert p.stderr is not None
					err = p.stderr.read()
				
				assert err is not None

				Logger.error("Encountered error in injected code")
				Logger.debug(err.decode('utf-8'))
				Logger.code(finalcode)
				exit(1)
		
		return None if out is None else out.decode('utf-8')

	def __popen_code(self, code: str, imports: Iterable[str] = []) -> tuple[Popen, str]:
		""" Popens custom php code with moodle context

		:param str code: the php code to execute
		:return tuple[Popen, str]: the running process and the bootstrapped code
		"""
		
		imports = ['config', *imports]
		
		bootstrap = """\
define('CLI_SCRIPT', true);
ini_set('display_errors', '1');
ini_set('display_startup_errors', '1');
error_reporting(E_ALL);
"""
		
		for i in imports:
			# TODO: check if file exists for better exception reporting
			fn = f"{i}.php"
			bootstrap += f"require_once('{pathjoin(self.moodledir, fn)}');"
		
		toexecute = f"{bootstrap}{code}"
		
		return Popen(
			["php", '-r', toexecute, '--'],
			stdout=PIPE, stderr=PIPE
		), toexecute

	def __run_script(self, name: SCRIPTNAME, params: Iterable[str], communicate: bool | str = False) -> str | None:
		""" Popens script and passes parameters to it

		:param SCRIPTNAME name: name of the script to execute
		:param Iterable[str] params: parameters to pass to the script
		:param bool|str communicate: whether to communicate with the script - will be passed to stdin if string
		:return str|None: stdout if communicate was true, None otherwise
		"""
  
		out: bytes | None = None
		err: bytes | None = None
		with self.__popen_script(name, params) as p:
			if communicate:
				out, err = p.communicate(communicate if isinstance(communicate, str) else None)
			
			if p.wait() != 0:
				if not communicate:
					assert p.stderr is not None
					err = p.stderr.read()
				
				assert err is not None

				Logger.error(f"Encountered error in script {name}:")
				Logger.debug(f"{err.decode('utf-8')}")
				Logger.debug(f"Script Parameters: {params}")
				exit(1)
		
		return None if out is None else out.decode('utf-8')

	def __popen_script(self, name: SCRIPTNAME, params: Iterable[str]) -> Popen:
		""" Popens script and passes parameters to it

		:param SCRIPTNAME name: name of the script to execute
		:param Iterable[str] params: parameters to pass to the script
		:return Popen: the running process
		"""
		return Popen(
			["php", '-f', pathjoin(self.script_folder, f"{name}.php"), '--', *params],
			stdout=PIPE, stderr=PIPE
		)
  
	def __run_webservice_function(self, function: str, parameters: dict, namespace: str = "local_lbplanner", as_user: int = 2) -> Any:
		""" Calls a moodle webservice function via CLI

		:param str functionname: the name of the function to call
		:param dict parameters: the parameters to pass to the function
		:param str namespace: the namespace of the function
		:param int as_user: the id of the user to run this as (1 means guest, 2 means admin, everything else is normal users)
		:return Popen: the running process
		"""
		Logger.debug(f"Calling webservice function {namespace}_{function} as user ID {as_user} with parameters {parameters}")
		# NOTE: this is mostly taken from external_api::call_external_function(…);
		json_data = self.__run_code(f"""\
			$USER = core_user::get_user({as_user}, '*', MUST_EXIST);
			$externalfunctioninfo = external_api::external_function_info('{namespace}_{function}');
			// validate parameters
			$callable = [$externalfunctioninfo->classname, 'validate_parameters'];
			$params = call_user_func(
                $callable,
                $externalfunctioninfo->parameters_desc,
                {php_serialize(parameters)}
            );
			$params = array_values($params);
			// call API function
			$result = call_user_func_array([$externalfunctioninfo->classname, $externalfunctioninfo->methodname], $params);
			// validate result
			if ($externalfunctioninfo->returns_desc !== null) {{
				$result = call_user_func([$externalfunctioninfo->classname, 'clean_returnvalue'], $externalfunctioninfo->returns_desc, $result);
			}}
			// return result
			echo json_encode($result);
			""",
			True,
			["lib/externallib"]
		)
  
		if json_data is None or len(json_data.strip()) == 0:
			Logger.debug("Webservice function returned no data")
			return None

		json_result = json.loads(json_data)
  
		if json_result is None:
			Logger.debug("Webservice function returned null")
			return None
  
		if 'error' in json_result:
			Logger.error(f"Webservice function {namespace}_{function} returned error: {json_result['error']['message']}")
			Logger.debug(json_data)
			exit(1)
  
		return json_result


	
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


