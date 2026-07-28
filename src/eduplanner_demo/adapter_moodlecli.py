from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .logger import Logger, redact
from .model import DemoConfig


JSON_MARKER = "__EDUPLANNER_DEMO_JSON__"


class MoodleError(RuntimeError):
    pass


class MoodleCLI:
    """Execute supported Moodle APIs from the container without requiring a user switch."""

    def __init__(self, moodle_dir: str | Path | None = None):
        self.moodle_dir = Path(moodle_dir or os.getenv("DEMO_MOODLE_DIR", "/bitnami/moodle")).resolve()
        self.config_php = self.moodle_dir / "config.php"

    def ready(self) -> bool:
        return self.config_php.is_file()

    def runtime_account(self) -> tuple[int, int, str]:
        configured = os.getenv("DEMO_MOODLE_USER", "daemon")
        try:
            account = pwd.getpwuid(int(configured)) if configured.isdigit() else pwd.getpwnam(configured)
        except KeyError as error:
            raise MoodleError(f"Moodle runtime user does not exist: {configured}") from error
        return account.pw_uid, account.pw_gid, account.pw_name

    def _command(self) -> list[str]:
        php = shutil.which("php") or "/opt/bitnami/php/bin/php"
        command = [php, "-r"]
        if os.geteuid() != 0 or not shutil.which("gosu"):
            return command
        _, group, name = self.runtime_account()
        return ["gosu", f"{name}:{group}", *command]

    def run_php(self, body: str, payload: Any = None) -> Any:
        if not self.ready():
            raise MoodleError(f"Moodle is not installed at {self.moodle_dir}")
        bootstrap = f"""
define('CLI_SCRIPT', true);
define('NO_OUTPUT_BUFFERING', true);
require {json.dumps(str(self.config_php))};
error_reporting(E_ALL);
ini_set('display_errors', 'stderr');
$USER = get_admin();
$inputjson = stream_get_contents(STDIN);
$input = $inputjson === '' ? [] : json_decode($inputjson, true, 512, JSON_THROW_ON_ERROR);
function demo_result(mixed $value): void {{
    echo "\\n{JSON_MARKER}" . json_encode($value, JSON_THROW_ON_ERROR) . "\\n";
}}
{body}
"""
        command = [*self._command(), bootstrap]
        Logger.debug(f"Moodle PHP command: {command[:2]} <php-code>")
        process = subprocess.run(
            command,
            input=json.dumps(payload or {}, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            Logger.debug(redact(process.stderr))
            raise MoodleError(
                f"Moodle PHP operation failed with exit code {process.returncode}: "
                f"{redact(process.stderr.strip() or process.stdout.strip())}"
            )
        marker = process.stdout.rfind(JSON_MARKER)
        if marker < 0:
            if process.stdout.strip():
                Logger.debug(process.stdout.strip())
            return None
        raw = process.stdout[marker + len(JSON_MARKER) :].strip().splitlines()[0]
        return json.loads(raw)

    def _configure_origin(self, base_url: str) -> bool:
        """Persist the selected public origin and proxy mode in Bitnami's config.php."""
        proxy_mode = urlparse(base_url).scheme == "https"
        escaped_url = base_url.replace("\\", "\\\\").replace("'", "\\'")
        start = "// BEGIN EDUPLANNER DEMO ORIGIN"
        end = "// END EDUPLANNER DEMO ORIGIN"
        block = (
            f"{start}\n"
            f"$CFG->wwwroot = '{escaped_url}';\n"
            f"$CFG->reverseproxy = {'true' if proxy_mode else 'false'};\n"
            f"$CFG->sslproxy = {'true' if proxy_mode else 'false'};\n"
            f"{end}"
        )
        source = self.config_php.read_text(encoding="utf-8")
        pattern = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
        if pattern.search(source):
            updated = pattern.sub(block, source)
        else:
            anchor = "require_once(__DIR__ . '/lib/setup.php');"
            if anchor not in source:
                raise MoodleError("Moodle config.php has no setup.php bootstrap anchor")
            updated = source.replace(anchor, f"{block}\n\n{anchor}", 1)
        if updated == source:
            return proxy_mode

        metadata = self.config_php.stat()
        descriptor, name = tempfile.mkstemp(prefix=".config.php.", dir=self.config_php.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, metadata.st_mode & 0o777)
            if os.geteuid() == 0:
                os.chown(temporary, metadata.st_uid, metadata.st_gid)
            os.replace(temporary, self.config_php)
        finally:
            temporary.unlink(missing_ok=True)
        return proxy_mode

    def configure(self, base_url: str) -> dict[str, Any]:
        proxy_mode = self._configure_origin(base_url)
        return self.run_php(
            r"""
global $CFG, $DB;
if (rtrim((string)$CFG->wwwroot, '/') !== $input['baseUrl']) {
    throw new moodle_exception('Configured Moodle wwwroot does not match DEMO_BASE_URL');
}
if ((bool)!empty($CFG->reverseproxy) !== (bool)$input['proxyMode'] ||
        (bool)!empty($CFG->sslproxy) !== (bool)$input['proxyMode']) {
    throw new moodle_exception('Moodle proxy settings do not match DEMO_BASE_URL');
}
set_config('enablewebservices', 1);
set_config('webserviceprotocols', 'rest');
set_config('debug', E_ALL);
set_config('debugdisplay', 1);
set_config('auth', implode(',', array_values(array_unique(array_filter([
    ...explode(',', (string)get_config('core', 'auth')),
    'manual',
    'edudemo',
])))));

$userrole = $DB->get_record('role', ['archetype' => 'user'], '*', MUST_EXIST);
assign_capability('moodle/webservice:createtoken', CAP_ALLOW, $userrole->id, context_system::instance()->id, true);
assign_capability('webservice/rest:use', CAP_ALLOW, $userrole->id, context_system::instance()->id, true);
accesslib_clear_all_caches(true);

$plugin = core_plugin_manager::instance()->get_plugin_info('local_lbplanner');
if (!$plugin) {
    throw new moodle_exception('LB Planner plugin is not installed');
}
$service = $DB->get_record('external_services', ['shortname' => 'lb_planner_sync_api'], '*', MUST_EXIST);
if (!$service->enabled) {
    $service->enabled = 1;
    $DB->update_record('external_services', $service);
}
demo_result([
    'moodleRelease' => $CFG->release,
    'pluginRelease' => $plugin->release,
    'serviceId' => $service->id,
    'baseUrl' => $input['baseUrl'],
]);
""",
            {"baseUrl": base_url, "proxyMode": proxy_mode},
        )

    def diagnostics(self) -> dict[str, Any]:
        return self.run_php(
            r"""
global $CFG, $DB;
$planner = core_plugin_manager::instance()->get_plugin_info('local_lbplanner');
$customfields = core_plugin_manager::instance()->get_plugin_info('local_modcustomfields');
$service = $DB->get_record('external_services', ['shortname' => 'lb_planner_sync_api']);
demo_result([
    'phpVersion' => PHP_VERSION,
    'moodleRelease' => $CFG->release,
    'siteUrl' => $CFG->wwwroot,
    'reverseProxy' => !empty($CFG->reverseproxy),
    'sslProxy' => !empty($CFG->sslproxy),
    'webServices' => !empty($CFG->enablewebservices),
    'restEnabled' => in_array('rest', array_filter(explode(',', (string)($CFG->webserviceprotocols ?? ''))), true),
    'serviceEnabled' => $service ? !empty($service->enabled) : false,
    'pluginRelease' => $planner ? $planner->release : null,
    'customFieldsVersion' => $customfields ? $customfields->versiondisk : null,
]);
"""
        )

    def enable_maintenance(self) -> None:
        self._run_cli("maintenance.php", "--enable")

    def disable_maintenance(self) -> None:
        self._run_cli("maintenance.php", "--disable")

    def purge_caches(self) -> None:
        self._run_cli("purge_caches.php")

    def _run_cli(self, script: str, *parameters: str) -> None:
        php = shutil.which("php") or "/opt/bitnami/php/bin/php"
        command = [php, str(self.moodle_dir / "admin" / "cli" / script), *parameters]
        if os.geteuid() == 0 and shutil.which("gosu"):
            _, group, name = self.runtime_account()
            command = ["gosu", f"{name}:{group}", *command]
        process = subprocess.run(command, text=True, capture_output=True, check=False)
        if process.returncode:
            raise MoodleError(redact(process.stderr.strip() or process.stdout.strip()))
        Logger.debug(process.stdout.strip())

    def reset(self) -> dict[str, int]:
        return self.run_php(
            r"""
global $CFG, $DB;
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/course/lib.php');
$deletedusers = 0;
$adminids = array_map('intval', array_keys(get_admins()));
foreach ($DB->get_records_select('user', 'id > 2 AND deleted = 0') as $user) {
    if (in_array((int)$user->id, $adminids, true)) {
        continue;
    }
    if (delete_user($user)) {
        $deletedusers++;
    }
}
$deletedcourses = 0;
foreach ($DB->get_records_select('course', 'id <> :siteid', ['siteid' => SITEID]) as $course) {
    delete_course($course, false);
    $deletedcourses++;
}
demo_result(['users' => $deletedusers, 'courses' => $deletedcourses]);
"""
        )

    def create_content(self, config: DemoConfig) -> dict[str, Any]:
        return self.run_php(
            r"""
global $CFG, $DB, $USER;
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->dirroot . '/group/lib.php');
require_once($CFG->dirroot . '/mod/quiz/locallib.php');
require_once($CFG->libdir . '/questionlib.php');

function edudemo_add_quiz_question(stdClass $quiz, int $cmid, string $activityname): void {
    $category = question_get_top_category(context_module::instance($cmid)->id, true);
    if (!$category) {
        throw new moodle_exception('Unable to create a question category for demo quiz');
    }

    $form = (object)[
        'category' => $category->id . ',' . $category->contextid,
        'name' => $activityname . ' demo question',
        'questiontext' => [
            'text' => 'This is an automatically generated EduPlanner demo question.',
            'format' => FORMAT_HTML,
        ],
        'defaultmark' => 1,
        'generalfeedback' => ['text' => '', 'format' => FORMAT_HTML],
        'correctanswer' => '1',
        'feedbacktrue' => ['text' => 'Correct.', 'format' => FORMAT_HTML],
        'feedbackfalse' => ['text' => 'Incorrect.', 'format' => FORMAT_HTML],
        'penalty' => 1,
        'status' => core_question\local\bank\question_version_status::QUESTION_STATUS_READY,
    ];
    $question = question_bank::get_qtype('truefalse')->save_question(
        (object)['qtype' => 'truefalse'],
        $form,
    );
    quiz_add_quiz_question($question->id, $quiz, 1, 1);
    mod_quiz\quiz_settings::create($quiz->id)->get_grade_calculator()->recompute_quiz_sumgrades();
}

$categoryid = core_course_category::get_default()->id;
$result = ['courses' => [], 'activities' => [], 'groups' => []];
$classes = [];
foreach ($input['users'] as $user) {
    if ($user['role'] !== 'student' || empty($user['class'])) {
        continue;
    }
    foreach ($user['courses'] as $courseid) {
        $classes[$courseid][$user['class']] = true;
    }
}

foreach ($input['courses'] as $courseinput) {
    $course = create_course((object)[
        'fullname' => $courseinput['name'],
        'shortname' => $courseinput['id'],
        'idnumber' => 'edudemo:' . $courseinput['id'],
        'category' => $categoryid,
        'enablecompletion' => 1,
        'startdate' => time(),
        'enddate' => 0,
    ]);
    $result['courses'][$courseinput['id']] = (int)$course->id;
    $result['groups'][$courseinput['id']] = [];
    foreach (array_keys($classes[$courseinput['id']] ?? []) as $classname) {
        $groupid = groups_create_group((object)[
            'courseid' => $course->id,
            'name' => $classname,
            'idnumber' => 'edudemo:' . $courseinput['id'] . ':' . $classname,
            'description' => 'EduPlanner demo class group',
            'descriptionformat' => FORMAT_PLAIN,
        ]);
        $result['groups'][$courseinput['id']][$classname] = (int)$groupid;
    }

    foreach ($courseinput['activities'] as $activityinput) {
        $modname = $activityinput['type'] === 'quiz' ? 'quiz' : 'assign';
        [$module, $context, $cw, $cm, $data] = prepare_new_moduleinfo_data($course, $modname, 1);
        $data->name = $activityinput['name'];
        $data->cmidnumber = '';
        $data->intro = $activityinput['description'];
        $data->introformat = FORMAT_HTML;
        $data->introeditor = [
            'text' => $activityinput['description'],
            'format' => FORMAT_HTML,
            'itemid' => 0,
        ];
        $data->completion = COMPLETION_TRACKING_MANUAL;
        if ($modname === 'assign') {
            $data->duedate = $activityinput['deadline'];
            $data->cutoffdate = 0;
            $data->gradingduedate = $activityinput['deadline'];
            $data->grade = 100;
            $data->allowsubmissionsfromdate = 0;
            $data->alwaysshowdescription = 1;
            $data->submissiondrafts = 0;
            $data->requiresubmissionstatement = 0;
            $data->sendnotifications = 0;
            $data->sendlatenotifications = 0;
            $data->teamsubmission = 0;
            $data->requireallteammemberssubmit = 0;
            $data->blindmarking = 0;
            $data->markingworkflow = 0;
            $data->markingallocation = 0;
        } else {
            $data->timeopen = 0;
            $data->timeclose = $activityinput['deadline'];
            $data->timelimit = 0;
            $data->overduehandling = 'autosubmit';
            $data->graceperiod = 0;
            $data->preferredbehaviour = 'deferredfeedback';
            $data->attempts = 0;
            $data->attemptonlast = 0;
            $data->grademethod = QUIZ_GRADEHIGHEST;
            $data->decimalpoints = 2;
            $data->questiondecimalpoints = -1;
            $data->grade = 100;
            $data->questionsperpage = 1;
            $data->navmethod = QUIZ_NAVMETHOD_FREE;
            $data->shuffleanswers = 1;
            $data->sumgrades = 0;
            foreach (['during', 'immediately', 'open', 'closed'] as $reviewstate) {
                foreach (['attempt', 'correctness', 'maxmarks', 'marks', 'specificfeedback',
                    'generalfeedback', 'rightanswer', 'overallfeedback'] as $reviewfield) {
                    $property = $reviewfield . $reviewstate;
                    $data->{$property} = ($reviewstate === 'during' && $reviewfield === 'overallfeedback') ? 0 : 1;
                }
            }
            $data->quizpassword = '';
            $data->subnet = '';
            $data->browsersecurity = '';
            $data->delay1 = 0;
            $data->delay2 = 0;
            $data->showuserpicture = 0;
            $data->showblocks = 0;
        }
        $created = add_moduleinfo($data, $course);
        $instanceid = (int)$created->instance;
        $cmid = (int)$created->coursemodule;
        if ($modname === 'quiz') {
            $quiz = $DB->get_record('quiz', ['id' => $instanceid], '*', MUST_EXIST);
            edudemo_add_quiz_question($quiz, $cmid, $activityinput['name']);
        }
        if (!empty($activityinput['classification'])) {
            $category = core_customfield\category_controller::create((int)get_config(
                'local_lbplanner',
                local_lbplanner\sync\classification::CONFIG_CATEGORY_ID,
            ));
            $savedclassification = false;
            foreach ($category->get_handler()->get_instance_data($cmid, true) as $fielddata) {
                if ($fielddata->get_field()->get('shortname') !== local_lbplanner\sync\classification::FIELD_SHORTNAME) {
                    continue;
                }
                $fielddata->set(
                    $fielddata->datafield(),
                    $fielddata->get_field()->parse_value($activityinput['classification']),
                );
                $fielddata->set('contextid', context_module::instance($cmid)->id);
                $fielddata->save();
                $savedclassification = true;
                break;
            }
            if (!$savedclassification) {
                throw new moodle_exception('LB Planner classification field was not found');
            }
        }
        $result['activities'][$activityinput['id']] = [
            'type' => $activityinput['type'],
            'instanceId' => $instanceid,
            'courseModuleId' => $cmid,
            'courseId' => (int)$course->id,
        ];
    }
}
demo_result($result);
""",
            config.as_wire_dict(),
        )

    def create_users(self, config: DemoConfig, content: dict[str, Any]) -> dict[str, int]:
        payload = config.as_wire_dict()
        payload["created"] = content
        return self.run_php(
            r"""
global $CFG, $DB, $USER;
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/group/lib.php');
require_once($CFG->dirroot . '/lib/enrollib.php');
$enrol = enrol_get_plugin('manual');
$studentrole = $DB->get_record('role', ['archetype' => 'student'], '*', MUST_EXIST);
$teacherrole = $DB->get_record('role', ['archetype' => 'editingteacher'], '*', MUST_EXIST);
$ids = [];
foreach ($input['users'] as $userinput) {
    $record = create_user_record($userinput['id'], $input['password'], 'manual');
    $parts = preg_split('/\s+/', trim($userinput['name']));
    $record->lastname = count($parts) > 1 ? array_pop($parts) : '-';
    $record->firstname = implode(' ', $parts) ?: $userinput['name'];
    $record->email = $userinput['id'] . '@example.invalid';
    $record->idnumber = 'edudemo:' . $userinput['id'];
    $record->address = $userinput['class'] ?? '';
    user_update_user($record, false, false);
    $ids[$userinput['id']] = (int)$record->id;
    foreach ($userinput['courses'] as $coursekey) {
        $courseid = $input['created']['courses'][$coursekey];
        $instance = $DB->get_record('enrol', ['courseid' => $courseid, 'enrol' => 'manual'], '*', MUST_EXIST);
        $roleid = $userinput['role'] === 'teacher' ? $teacherrole->id : $studentrole->id;
        $enrol->enrol_user($instance, $record->id, $roleid, 0, 0, ENROL_USER_ACTIVE);
        if ($userinput['role'] === 'student' && !empty($userinput['class'])) {
            $groupid = $input['created']['groups'][$coursekey][$userinput['class']] ?? null;
            if ($groupid) {
                groups_add_member($groupid, $record->id);
            }
        }
    }
}
set_config('credentials', json_encode(array_map(
    fn($user) => ['name' => $user['name'], 'username' => $user['id'], 'password' => $input['password']],
    $input['users']
)), 'local_edudemo');
demo_result($ids);
""",
            payload,
        )

    def apply_states(
        self, config: DemoConfig, content: dict[str, Any], users: dict[str, int]
    ) -> dict[str, int]:
        payload = config.as_wire_dict()
        payload["created"] = content
        payload["userIds"] = users
        return self.run_php(
            r"""
global $CFG, $DB, $USER;
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/mod/quiz/locallib.php');
$submitted = 0;
$completed = 0;
foreach ($input['users'] as $userinput) {
    $userid = $input['userIds'][$userinput['id']];
    $USER = core_user::get_user($userid, '*', MUST_EXIST);
    foreach ($userinput['taskStatus'] as $taskid => $status) {
        $activity = $input['created']['activities'][$taskid];
        $cm = get_coursemodule_from_id('', $activity['courseModuleId'], 0, false, MUST_EXIST);
        $course = get_course($activity['courseId']);
        $context = context_module::instance($cm->id);
        if ($activity['type'] === 'assignment') {
            $assignment = new assign($context, $cm, $course);
            $submission = $assignment->get_user_submission($userid, true);
            $submission->status = ASSIGN_SUBMISSION_STATUS_SUBMITTED;
            $submission->timemodified = time();
            $DB->update_record('assign_submission', $submission);
            if ($status === 'completed') {
                $grade = $assignment->get_user_grade($userid, true);
                $grade->grade = 100;
                $grade->grader = 2;
                $grade->timemodified = time();
                $assignment->update_grade($grade);
            }
        } else {
            $quizobj = mod_quiz\quiz_settings::create($activity['instanceId'], $userid);
            $attempt = quiz_prepare_and_start_new_attempt($quizobj, 1, null, false);
            $attemptobj = mod_quiz\quiz_attempt::create($attempt->id);
            $attemptobj->process_submitted_actions(time(), false, [
                1 => ['answer' => $status === 'completed' ? '1' : '0'],
            ]);
            $attemptobj->process_finish(time(), false);
        }
        $submitted++;
        if ($status === 'completed') {
            $completion = new completion_info($course);
            $completion->update_state($cm, COMPLETION_COMPLETE, $userid);
            $completed++;
        }
    }
}
demo_result(['submitted' => $submitted, 'completed' => $completed]);
""",
            payload,
        )

    def internal_doctor(self, representative_user_id: int) -> dict[str, Any]:
        return self.run_php(
            r"""
global $CFG, $USER;
require_once($CFG->libdir . '/externallib.php');
$USER = core_user::get_user($input['userId'], '*', MUST_EXIST);
$functions = [
    'local_lbplanner_sync_get_identity',
    'local_lbplanner_sync_get_courses',
    'local_lbplanner_sync_get_assignments',
    'local_lbplanner_sync_get_quizzes',
];
$result = [];
foreach ($functions as $function) {
    $info = external_api::external_function_info($function);
    $value = call_user_func([$info->classname, $info->methodname]);
    $result[$function] = is_array($value) ? count($value) : $value;
}
demo_result($result);
""",
            {"userId": representative_user_id},
        )
