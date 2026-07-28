<?php
require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/locallib.php');

require_login();
$context = context_system::instance();
require_capability('moodle/site:config', $context);

$PAGE->set_context($context);
$PAGE->set_url(new moodle_url('/local/edudemo/index.php'));
$PAGE->set_title(get_string('configtitle', 'local_edudemo'));
$PAGE->set_heading(get_string('configtitle', 'local_edudemo'));

$PAGE->requires->js_call_amd('local_edudemo/editor', 'init', [sesskey()]);

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('configtitle', 'local_edudemo'));
echo html_writer::tag('p', get_string('configdescription', 'local_edudemo'), ['class' => 'alert alert-warning']);
echo html_writer::div('', '', ['id' => 'edudemo-editor']);
echo $OUTPUT->footer();
