# EduPlanner Demo

This is a demo project for EduPlanner, an educational planning tool. The project includes sample courses, tasks, and user configurations to showcase the capabilities of EduPlanner.

## Development Setup

### Getting Started

We're using hatchling - all you have to run is `python3 -m build` to build the package,
and `python3 -m hatch shell` to enter the development environment containing all necessary dependencies and such.

### Modifying Course and Task Configurations

The course and task configurations are located in the `config/courses.yml` file. You can modify this file to add or change courses and tasks as needed. User configurations are in the `config/users.yml` file. Note that the schema for user configurations is auto-generated in `src/eduplanner_demo/autocomplete.py` to ensure that task IDs correspond to existing tasks. If you add new tasks, make sure to update the schema accordingly by running the autocomplete script (vscode should do this automatically if you've installed the recommended extensions).
