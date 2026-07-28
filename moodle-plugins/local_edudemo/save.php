<?php
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');
require_once(__DIR__ . '/locallib.php');

require_login();
require_capability('moodle/site:config', context_system::instance());
require_sesskey();

header('Content-Type: application/json');
try {
    $request = json_decode(file_get_contents('php://input'), true, 512, JSON_THROW_ON_ERROR);
    $result = local_edudemo_agent_request([
        'operation' => 'save',
        'courses' => $request['courses'] ?? null,
        'users' => $request['users'] ?? null,
    ]);
    echo json_encode(['ok' => true, 'result' => $result], JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => $error->getMessage()], JSON_THROW_ON_ERROR);
}
