# EduPlanner Demo

A disposable Moodle 4.4 environment for exercising the LB Planner 2.0 read-only sync API. It creates native Moodle courses, groups, assignments, quizzes, submissions, attempts, completion state, and activity classifications, then verifies the four token-scoped sync resources.

> **Destructive demo only:** every configuration apply deletes every Moodle course and every non-admin user. The image is based on the archived Bitnami 4.4 image and must not be used as production infrastructure or exposed without access controls.

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

No Moodle administration clicks, Hatch shell, manual plugin copy, filesystem `chmod`, or container-user switch is required.

To remove the complete disposable environment:

```shell
docker compose down -v
```

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
