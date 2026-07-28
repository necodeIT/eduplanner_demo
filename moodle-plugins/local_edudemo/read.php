<?php
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/locallib.php');

require_login();
require_capability('moodle/site:config', context_system::instance());

header('Content-Type: application/json');
try {
    echo json_encode([
        'ok' => true,
        'result' => local_edudemo_agent_request(['operation' => 'read']),
    ], JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    http_response_code(503);
    echo json_encode(['ok' => false, 'error' => $error->getMessage()], JSON_THROW_ON_ERROR);
}
