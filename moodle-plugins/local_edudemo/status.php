<?php
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/locallib.php');

require_login();
require_capability('moodle/site:config', context_system::instance());
header('Content-Type: application/json');
echo json_encode(local_edudemo_agent_request(['operation' => 'status']), JSON_THROW_ON_ERROR);
