FROM bitnami/moodle:latest


RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y pip
RUN pip install hatch --break-system-packages
RUN apt-get install -y python3-build

COPY ./ pallasys/cli
WORKDIR /pallasys/cli
RUN python3 -m build
RUN mkdir -p /home/daemon
RUN chown daemon:daemon /home/daemon

WORKDIR /

EXPOSE 8080 8443

ENTRYPOINT [ "/opt/bitnami/scripts/moodle/entrypoint.sh" ]
CMD [ "/opt/bitnami/scripts/moodle/run.sh" ]