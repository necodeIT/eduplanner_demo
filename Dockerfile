# syntax=docker/dockerfile:1.7

FROM composer:2 AS plugin-builder
WORKDIR /work
COPY --from=lbplanner /composer.json ./
COPY --from=lbplanner /lbplanner ./lbplanner
RUN composer update --no-dev --no-ansi --no-interaction --no-scripts --no-progress --prefer-dist --optimize-autoloader

FROM scratch AS modcustomfields
ADD --checksum=sha256:873926a08589713a7d7f79629bb7e12c1b05ff429040188e1240878fe8d6aaef \
    https://gitlab.com/adapta/moodle-local_modcustomfields/-/archive/13ba97ee/moodle-local_modcustomfields-13ba97ee.tar.gz \
    /modcustomfields.tar.gz

FROM bitnamilegacy/moodle:4.4.4-debian-12-r4@sha256:1e8ba5393f4cfec9e1151ca31b8f38600e4566e189cb754903667bca19e10b0b

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
    PYTHONUNBUFFERED=1

WORKDIR /
EXPOSE 8080
ENTRYPOINT ["/opt/eduplanner-demo/docker/entrypoint.sh"]
CMD ["/opt/bitnami/scripts/moodle/run.sh"]
