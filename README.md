# EduPlanner Demo

This is a demo project for EduPlanner, an educational planning tool. The project includes sample courses, tasks, and user configurations to showcase the capabilities of EduPlanner.

## Development Setup

### Getting Started

This project requires Python 3.10 or higher. It is recommended to use a virtual environment to manage dependencies.

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
pip install -r requirements.txt
```

Alternatively, you can run the setup script which will create a virtual environment and install the dependencies for you:

```bash
bash setup.sh
```

### Modifying Course and Task Configurations

The course and task configurations are located in the `config/courses.yml` file. You can modify this file to add or change courses and tasks as needed. User configurations are in the `config/users.yml` file. Note that the schema for user configurations is auto-generated in `bin/autocomplete.py` to ensure that task IDs correspond to existing tasks. If you add new tasks, make sure to update the schema accordingly by running the autocomplete script (vscode should do this automatically if you've installed the recommended extensions).
