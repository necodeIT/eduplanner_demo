<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $ADMIN->add('localplugins', new admin_externalpage(
        'local_edudemo_config',
        get_string('configtitle', 'local_edudemo'),
        new moodle_url('/local/edudemo/index.php'),
        'moodle/site:config'
    ));
}
