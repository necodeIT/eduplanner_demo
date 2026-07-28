<?php
defined('MOODLE_INTERNAL') || die();

class auth_plugin_edudemo extends auth_plugin_base {
    public function __construct() {
        $this->authtype = 'edudemo';
        $this->config = get_config('auth_edudemo');
    }

    public function user_login($username, $password): bool {
        return false;
    }

    public function is_internal(): bool {
        return false;
    }

    public function can_be_manually_set(): bool {
        return false;
    }

    public function loginpage_hook(): void {
        global $PAGE;

        $raw = get_config('local_edudemo', 'credentials');
        $credentials = json_decode((string) $raw, true);
        if (!is_array($credentials) || !$credentials) {
            return;
        }
        $PAGE->requires->js_call_amd('auth_edudemo/selector', 'init', [$credentials]);
    }
}
