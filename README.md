# EduPlanner Demo

A disposable Moodle 4.4 environment for exercising the LB Planner 2.0 read-only sync API. It creates native Moodle courses, groups, assignments, quizzes, submissions, attempts, completion state, and activity classifications, then verifies the four token-scoped sync resources.

> **Destructive demo only:** every configuration apply deletes every Moodle
> course and every non-admin user. The image is based on the archived Bitnami
> 4.4 image and must never contain production data or serve as production
> infrastructure. A public customer demo must remain disposable and sit behind
> the documented TLS ingress and rate limits.

## Start locally

The example environment is ready for direct local access:

```shell
cp .env.example .env
docker compose up --build -d
```

Open [http://localhost:420](http://localhost:420). Local mode accepts only loopback HTTP origins (`localhost` or `127.0.0.1`) and automatically disables Moodle's reverse-proxy and SSL-proxy flags. Switching an existing named-volume installation between local and proxy modes rewrites its persisted canonical origin on startup; deleting volumes is not required.

Compose always builds the `eduplanner_demo-moodle` application image locally. It does not pull or push that application image. During the build, BuildKit fetches LB Planner directly from GitHub and downloads the pinned Moodle, MariaDB, Composer, and Dockerfile frontend base images when they are not already cached locally.

For HTTPS reverse-proxy testing, set `DEMO_BASE_URL` to the public HTTPS origin. The proxy should forward it to `http://127.0.0.1:420`, set the upstream `Host` to an internal name (for example `127.0.0.1:420`), and set `X-Forwarded-Proto: https`. Moodle 4.4 rejects the public host on the upstream request when reverse-proxy mode is enabled. TLS terminates at the proxy, and Moodle generates canonical URLs from `DEMO_BASE_URL`.

On every image start the container automatically:

1. installs or upgrades `local_modcustomfields`, LB Planner, and the two demo companion plugins;
2. enables REST web services and token creation;
3. validates YAML and regenerates JSON schemas;
4. populates Moodle when the config/populator hash changed; and
5. watches both config files and reapplies valid changes once they settle.

After every successful population it also writes the private versioned
integration manifest to
`/var/lib/eduplanner-demo/integration-manifest.json`. The atomic file is mode
`0600` and includes all configured non-admin users plus their personal LB
Planner tokens for the EduPlanner server provisioner. It must be mounted only
through a private state volume: no command prints it, no web route serves it,
and it must never be copied into an image or logs.

No Moodle administration clicks, Hatch shell, manual plugin copy, filesystem `chmod`, or container-user switch is required.

To remove the complete disposable environment:

```shell
docker compose down -v
```

## Environment variables

Copy `.env.example` to `.env` for standalone use. The file is local operator
configuration and must not be committed when it contains a real administrator
password.

| Variable | Required | Meaning |
| --- | --- | --- |
| `DEMO_BASE_URL` | Yes | Canonical public Moodle origin. Use exactly `http://localhost:420` (or `127.0.0.1`) locally, or an HTTPS origin without a path, query, fragment, credentials, or trailing slash. |
| `MOODLE_ADMIN_PASSWORD` | Shared environments | Moodle administrator password. Standalone local Compose defaults to `test`; never rely on that default for a customer demo. |
| `LBPLANNER_REF` | Image releases | LB Planner tag, branch, or commit selected at build time. Hosted images must use a full 40-character commit SHA; standalone local builds default to `main`. |

The image also defines implementation variables that Compose already wires and
operators should not normally override:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DEMO_INTERNAL_HTTP_PORT` | `8080` | Container-local Apache port used by the post-start `demo doctor` REST checks. This is not the published host port `420`. |
| `DEMO_CONFIG_DIR` | `/opt/eduplanner-demo/config` | Directory containing `courses.yml` and `users.yml`. |
| `DEMO_SCHEMA_DIR` | `/opt/eduplanner-demo/schema` | Generated JSON-schema directory. |
| `DEMO_STATE_DIR` | `/var/lib/eduplanner-demo` | Private status, lock, and integration-manifest volume. |
| `DEMO_MOODLE_DIR` | `/bitnami/moodle` | Moodle installation directory. |
| `DEMO_MOODLE_USER` | `daemon` | Account used for Moodle CLI operations. |
| `DEMO_AGENT_SOCKET` | `/run/eduplanner-demo/agent.sock` | Private configuration-editor Unix socket. |
| `DEMO_LBPLANNER_REF` | baked into image | Selected plugin revision recorded in diagnostics and the deterministic population hash. |

MariaDB and `MOODLE_*` installation variables in `docker-compose.yml` are
Bitnami container inputs. In the combined EduPlanner stack they are supplied by
`tool/eduplanner`; do not add them separately to the server's `.env.local`.

## HTTP diagnostics

Initial population runs before Apache starts. Integration-manifest tokens are
therefore created through Moodle's CLI bootstrap using the same core token
utility as `login/token.php`; population does not depend on HTTP, public DNS, or
TLS ingress. If startup logs show `/login/token.php` retries while creating the
manifest, the container is running an older image and must be rebuilt.

The operator-run `demo doctor` command does exercise REST through
`127.0.0.1:8080` inside the running Moodle container; it does not call the
public `:420` mapping. Connection failures, malformed responses, HTTP `408`,
`425`, `429`, and common `5xx` responses are retried six times with bounded
backoff. Permanent `4xx` responses fail immediately. Form fields and response
bodies are never logged, because they can contain passwords or personal
web-service tokens.

Use these redacted diagnostics first:

```shell
docker compose ps
docker compose logs --tail=200 moodle mariadb
docker compose exec moodle demo status
docker compose exec moodle demo doctor
```

- Repeated `connection failure` or `HTTP 502/503` usually means Apache/PHP or
  MariaDB did not become stable. Check the first fatal error in the Moodle and
  MariaDB logs, then restart the Moodle service.
- An Apache access-log line such as `"-" 408 -` is not a population request.
  It means a port probe opened a TCP connection without sending HTTP. If
  `demo status --check` succeeds, this line can be ignored or traced to the
  external probe.
- `invalid JSON response` usually means Apache returned an HTML error page.
  Inspect the Moodle log around the same timestamp; the response body is
  intentionally suppressed.
- `HTTP 400/403` usually indicates a canonical-origin/reverse-proxy mismatch or
  a disabled web-service endpoint. Confirm `DEMO_BASE_URL` follows the exact
  origin rules above and run `demo doctor`.
- `HTTP 404` commonly indicates an incomplete/old plugin image. Rebuild using an
  LB Planner revision that contains the 2.0 sync contract.

After correcting the cause, `docker compose restart moodle` reruns the normal
entrypoint. If status remains `failed`, `docker compose exec moodle demo apply`
retries population. That apply is intentionally destructive to all non-admin
users and courses in this disposable Moodle instance.

## `demo` CLI

The image installs one executable:

```shell
docker compose exec moodle demo status
docker compose exec moodle demo validate
docker compose exec moodle demo schema
docker compose exec moodle demo apply --force
docker compose exec moodle demo doctor
docker compose exec moodle demo credentials
```

- `apply` skips an unchanged hash; `--force` always performs the destructive reset.
- `doctor` obtains a real user token and calls identity, courses, assignments, and quizzes through Moodle REST.
- `credentials` is the only command that deliberately prints the shared password. Normal and verbose logs redact passwords and tokens.
- Interactive terminals get progress spinners and timings; container logs receive timestamped stage, count, duration, and error lines.

## Configuration

Only `config/courses.yml` and `config/users.yml` remain. Plans and slots were removed in LB Planner 2.0 and have no demo representation.

Course activities use the sync resource type and optional LB Planner classification:

```yaml
courses:
  - name: Mathematics
    tasks:
      - name: Midterm Exam
        description: Exam on limits and derivatives.
        due: 10
        type: quiz
        classification: TEST
```

Users declare their native Moodle enrolments explicitly. Student classes become real Moodle groups in every enrolled course. Missing task status means pending.

```yaml
password: "1234"
users:
  - name: Alice Johnson
    role: student
    class: 1AHIT
    courses: [mathematics]
    task-status:
      mathematics.midterm_exam: completed
```

Valid activity types are `assignment` and `quiz`. Valid classifications are `GK`, `EK`, `TEST`, `M`, or an omitted/null value. Valid explicit task states are `submitted` and `completed`.

The watcher validates the complete candidate before deleting data. Invalid edits leave the currently populated Moodle data intact and appear in `demo status`.

## Browser tools

The Moodle login page contains a demo-account selector. It lists configured demo users, never admin or guest, and fills the normal username/password fields without submitting the form.

Site administrators can open **Site administration → Plugins → Local plugins → EduPlanner demo configuration** for a structured courses/users editor. Saving is validated through a constrained Unix-socket agent, updates the YAML and schemas atomically, and queues one watched apply. Moodle's existing admin session protects the editor; there is no second identity provider or webserver.

## Plugin source and image builds

Builds fetch LB Planner directly from `necodeIT/lb_planner_plugin` on GitHub. No adjacent plugin checkout is required. The default ref is `main`; use `LBPLANNER_REF` to select a release tag, branch, or full 40-character commit SHA:

```shell
LBPLANNER_REF=v2.0.0 docker compose build moodle
LBPLANNER_REF=25eae44bc48b628798f4028f68a4f972b578356e docker compose build moodle
```

You can also put the selection in `.env`:

```dotenv
LBPLANNER_REF=25eae44bc48b628798f4028f68a4f972b578356e
```

The resulting image contains the selected source and its production Composer dependencies. Changing `LBPLANNER_REF`, or rebuilding after the selected branch advances, incorporates the new plugin source. CI uses the same remote Git context and accepts an optional `lbplanner_ref` input when started manually.

The selected ref must contain the LB Planner 2.0 sync contract. The build checks this before installing Composer dependencies and reports an actionable error when an older ref is selected.

## Development checks

Python tests can be run with any Python 3.11+ environment:

```shell
python -m pip install -e . pytest
pytest
demo --config config --schema-dir schema validate
```
