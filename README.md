# EduPlanner Demo

This is a demo project for EduPlanner, an educational planning tool. The project includes sample courses, tasks, and user configurations to showcase the capabilities of EduPlanner.

## Development Setup

### Prerequisites

- python-hatch: `pacman -S python-hatch`
- python-build: `pacman -S python-build`

### Getting Started

We're using hatchling - all you have to run is `python3 -m build` to build the package,
and `python3 -m hatch shell` to enter the development environment containing all necessary dependencies and such.

### Modifying Course and Task Configurations

The course and task configurations are located in the `config/courses.yml` file. You can modify this file to add or change courses and tasks as needed. User configurations are in the `config/users.yml` file. Note that the schema for user configurations is auto-generated via `eduplanner_demo schemagen` to ensure that task IDs correspond to existing tasks. If you add new tasks, make sure to update the schema accordingly by running the command (vscode should do this automatically if you've installed the recommended extensions).

### Testing Containers

You can use the provided docker-compose setup to run test containers for a moodle test server and mariadb instance.

Run the following commands to start the containers (or alternatively use `./up.sh`):

```bash
mkdir -p .dev/mariadb_data
sudo chmod -R 777 .dev/mariadb_data
docker-compose up -d
```

To whipe the installation, you can run the following commands (or alternatively use `./destroy.sh`):

```bash
docker-compose down
sudo rm -rf .dev
```

### Preparing your Moodle Instance

TODO: automate these processes

Before you can run the demo script, you need to

- install the [eduplanner plugin](https://github.com/necodeIT/lb_planner_plugin/)
- create roles for the included capabilities (student, teacher, slotmaster)
  The names of these roles are not important - as long as there's one for each capability, the script will find the correct roles to use.
- if you want to debug errors, you should also enable error reporting in moodle, otherwise the script will not be able to report any details about errors

after this, the script should be able to handle everything itself.
