<?php
defined('MOODLE_INTERNAL') || die();

function local_edudemo_agent_request(array $request): array {
    $path = getenv('DEMO_AGENT_SOCKET') ?: '/run/eduplanner-demo/agent.sock';
    $errornumber = 0;
    $error = '';
    $socket = @stream_socket_client(
        'unix://' . $path,
        $errornumber,
        $error,
        5,
        STREAM_CLIENT_CONNECT
    );
    if (!$socket) {
        throw new moodle_exception('agenterror', 'local_edudemo', '', $error ?: $errornumber);
    }
    stream_set_timeout($socket, 30);
    fwrite($socket, json_encode($request, JSON_THROW_ON_ERROR) . "\n");
    $response = fgets($socket, 4 * 1024 * 1024);
    fclose($socket);
    if ($response === false) {
        throw new moodle_exception('agenterror', 'local_edudemo', '', 'empty response');
    }
    $decoded = json_decode($response, true, 512, JSON_THROW_ON_ERROR);
    if (empty($decoded['ok'])) {
        throw new moodle_exception('agenterror', 'local_edudemo', '', $decoded['error'] ?? 'unknown error');
    }
    return $decoded['result'];
}
