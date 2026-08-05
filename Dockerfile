# syntax=docker/dockerfile:1.7

FROM composer:2 AS plugin-builder
ARG LBPLANNER_REF=main
WORKDIR /work
COPY --from=lbplanner /composer.json ./
COPY --from=lbplanner /composer.lock ./
COPY --from=lbplanner /lbplanner ./lbplanner
RUN php <<'PHP'
<?php
$composer = json_decode(file_get_contents('composer.json'), true);
$replace = array_keys($composer['replace'] ?? []);
$lock = json_decode(file_get_contents('composer.lock'), true);
$lock['packages'] = array_values(array_filter(
    $lock['packages'] ?? [],
    static fn (array $package): bool => !in_array($package['name'] ?? '', $replace, true),
));
file_put_contents(
    'composer.lock',
    json_encode($lock, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL,
);
PHP
RUN test -f lbplanner/classes/sync/provider.php && \
    test -f lbplanner/classes/sync/contract.php || \
    (printf 'ERROR: LBPLANNER_REF=%s does not contain the LB Planner 2.0 sync contract.\n' "$LBPLANNER_REF" >&2; \
     printf 'Choose a 2.0 release tag, branch, or full commit SHA with LBPLANNER_REF.\n' >&2; \
     exit 1) && \
    composer install --no-dev --no-ansi --no-interaction --no-scripts --no-progress --prefer-dist --optimize-autoloader

FROM scratch AS modcustomfields
ADD --checksum=sha256:873926a08589713a7d7f79629bb7e12c1b05ff429040188e1240878fe8d6aaef \
    https://gitlab.com/adapta/moodle-local_modcustomfields/-/archive/13ba97ee/moodle-local_modcustomfields-13ba97ee.tar.gz \
    /modcustomfields.tar.gz

FROM bitnamilegacy/moodle:4.4.4-debian-12-r4@sha256:1e8ba5393f4cfec9e1151ca31b8f38600e4566e189cb754903667bca19e10b0b

ARG LBPLANNER_REF=main
LABEL org.opencontainers.image.lbplanner-ref=$LBPLANNER_REF

USER root
RUN install_packages gosu patch python3 python3-pip rsync tar

WORKDIR /opt/eduplanner-demo
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY schema ./schema
COPY docker ./docker
COPY moodle-plugins ./moodle-plugins
COPY --from=plugin-builder /work/lbplanner ./plugins/lbplanner
COPY --from=modcustomfields /modcustomfields.tar.gz /tmp/modcustomfields.tar.gz
RUN mkdir -p plugins/modcustomfields && \
    tar -xzf /tmp/modcustomfields.tar.gz --strip-components=1 -C plugins/modcustomfields && \
    rm /tmp/modcustomfields.tar.gz && \
    patch -d plugins/lbplanner -p1 < docker/lbplanner-externallib.patch && \
    find plugins moodle-plugins -type d -exec chmod 0755 {} + && \
    find plugins moodle-plugins -type f -exec chmod 0644 {} + && \
    pip3 install --break-system-packages --no-cache-dir . && \
    chmod +x docker/entrypoint.sh docker/start.sh docker/moodle-setup.sh && \
    install -m 0755 docker/start.sh /post-init.sh && \
    mv /opt/bitnami/scripts/moodle/setup.sh /opt/bitnami/scripts/moodle/setup-bitnami.sh && \
    install -m 0755 docker/moodle-setup.sh /opt/bitnami/scripts/moodle/setup.sh && \
    mkdir -p /run/eduplanner-demo /var/lib/eduplanner-demo && \
    rsync -a plugins/lbplanner/ /opt/bitnami/moodle/local/lbplanner/ && \
    rsync -a plugins/modcustomfields/ /opt/bitnami/moodle/local/modcustomfields/ && \
    rsync -a moodle-plugins/auth_edudemo/ /opt/bitnami/moodle/auth/edudemo/ && \
    rsync -a moodle-plugins/local_edudemo/ /opt/bitnami/moodle/local/edudemo/

ENV DEMO_CONFIG_DIR=/opt/eduplanner-demo/config \
    DEMO_SCHEMA_DIR=/opt/eduplanner-demo/schema \
    DEMO_STATE_DIR=/var/lib/eduplanner-demo \
    DEMO_AGENT_SOCKET=/run/eduplanner-demo/agent.sock \
    DEMO_MOODLE_DIR=/bitnami/moodle \
    DEMO_LBPLANNER_REF=$LBPLANNER_REF \
    PYTHONUNBUFFERED=1

WORKDIR /
EXPOSE 8080
ENTRYPOINT ["/opt/eduplanner-demo/docker/entrypoint.sh"]
CMD ["/opt/bitnami/scripts/moodle/run.sh"]
