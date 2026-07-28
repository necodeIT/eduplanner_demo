define([], function() {
    const element = (tag, attrs = {}, children = []) => {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([key, value]) => {
            if (key === 'className') node.className = value;
            else if (key === 'text') node.textContent = value;
            else node.setAttribute(key, value);
        });
        children.forEach((child) => node.append(child));
        return node;
    };
    const input = (value, onChange, type = 'text') => {
        const node = element('input', {className: 'form-control', type, value: value ?? ''});
        node.addEventListener('input', () => onChange(type === 'number' ? Number(node.value) : node.value));
        return node;
    };
    const select = (value, options, onChange, allowBlank = false) => {
        const node = element('select', {className: 'form-control'});
        if (allowBlank) node.append(element('option', {value: '', text: '—'}));
        options.forEach((option) => node.append(element('option', {value: option, text: option})));
        node.value = value ?? '';
        node.addEventListener('change', () => onChange(node.value || null));
        return node;
    };
    const field = (label, control) => element('div', {className: 'form-group'}, [
        element('label', {text: label}), control,
    ]);
    const button = (label, style, action) => {
        const node = element('button', {type: 'button', className: `btn ${style} mr-2`, text: label});
        node.addEventListener('click', action);
        return node;
    };
    const slug = (value) => (value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
        .toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

    const init = async(sesskey) => {
        const root = document.getElementById('edudemo-editor');
        root.append(element('div', {className: 'alert alert-info', text: 'Loading demo configuration…'}));
        let initial;
        try {
            const response = await fetch('read.php', {headers: {'Accept': 'application/json'}});
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || response.statusText);
            }
            initial = payload.result;
        } catch (error) {
            root.replaceChildren(element('div', {
                className: 'alert alert-danger',
                text: `Could not load the demo configuration: ${error.message}`,
            }));
            return;
        }
        const state = {courses: initial.courses, users: initial.users, status: initial.status, tab: 'courses'};
        const rerender = () => {
            root.replaceChildren();
            const toolbar = element('div', {className: 'mb-3'}, [
                button('Save and apply', 'btn-primary', save),
                button('Add course', 'btn-secondary', () => {
                    state.courses.courses.push({name: 'New course', tasks: []}); rerender();
                }),
                button('Add user', 'btn-secondary', () => {
                    state.users.users.push({name: 'New user', role: 'student', class: '1AHIT', courses: [], 'task-status': {}}); rerender();
                }),
            ]);
            const tabs = element('div', {className: 'btn-group mb-3'}, [
                button('Courses', state.tab === 'courses' ? 'btn-primary' : 'btn-outline-primary', () => {
                    state.tab = 'courses'; rerender();
                }),
                button('Users', state.tab === 'users' ? 'btn-primary' : 'btn-outline-primary', () => {
                    state.tab = 'users'; rerender();
                }),
            ]);
            root.append(toolbar, statusPanel(), tabs);
            if (state.tab === 'courses') {
                state.courses.courses.forEach((course, courseIndex) => root.append(courseCard(course, courseIndex)));
            } else {
                root.append(field('Shared demo password', input(
                    state.users.password,
                    (value) => state.users.password = value,
                    'password',
                )));
                state.users.users.forEach((user, userIndex) => root.append(userCard(user, userIndex)));
            }
        };
        const statusPanel = () => element('pre', {
            'data-edudemo-status': 'true',
            className: `alert ${state.status.state === 'ready' ? 'alert-success' : 'alert-info'}`,
            text: JSON.stringify(state.status, null, 2),
        });
        const courseCard = (course, index) => {
            const card = element('section', {className: 'card card-body mb-3'});
            card.append(field('Course name', input(course.name, (value) => course.name = value)));
            course.tasks.forEach((task, taskIndex) => {
                const taskNode = element('div', {className: 'border rounded p-3 mb-2'});
                taskNode.append(
                    field('Task name', input(task.name, (value) => task.name = value)),
                    field('Type', select(task.type, ['assignment', 'quiz'], (value) => task.type = value)),
                    field('Classification', select(task.classification, ['GK', 'EK', 'TEST', 'M'], (value) => task.classification = value, true)),
                    field('Due in days', input(task.due, (value) => task.due = value, 'number')),
                    field('Description', input(task.description, (value) => task.description = value)),
                    button('Remove task', 'btn-outline-danger', () => {course.tasks.splice(taskIndex, 1); rerender();}),
                );
                card.append(taskNode);
            });
            card.append(
                button('Add task', 'btn-outline-secondary', () => {
                    course.tasks.push({name: 'New task', description: '', due: 1, type: 'assignment', classification: null}); rerender();
                }),
                button('Remove course', 'btn-outline-danger', () => {state.courses.courses.splice(index, 1); rerender();}),
            );
            return card;
        };
        const userCard = (user, index) => {
            const card = element('section', {className: 'card card-body mb-3'});
            card.append(
                field('Name', input(user.name, (value) => user.name = value)),
                field('Role', select(user.role, ['student', 'teacher'], (value) => {user.role = value; rerender();})),
                field('Class', input(user.class, (value) => user.class = value)),
            );
            const courseSelect = element('select', {className: 'form-control', multiple: 'multiple', size: '5'});
            state.courses.courses.forEach((course) => {
                const id = slug(course.name);
                const option = element('option', {value: id, text: `${course.name} (${id})`});
                option.selected = (user.courses || []).includes(id);
                courseSelect.append(option);
            });
            courseSelect.addEventListener('change', () => {
                user.courses = Array.from(courseSelect.selectedOptions).map((option) => option.value);
                rerender();
            });
            card.append(field('Courses', courseSelect));
            user['task-status'] = user['task-status'] || {};
            if (user.role !== 'student') {
                user['task-status'] = {};
                card.append(button('Remove user', 'btn-outline-danger', () => {state.users.users.splice(index, 1); rerender();}));
                return card;
            }
            state.courses.courses.forEach((course) => {
                const courseId = slug(course.name);
                if (!(user.courses || []).includes(courseId)) return;
                course.tasks.forEach((task) => {
                    const taskId = `${courseId}.${slug(task.name)}`;
                    card.append(field(`Status: ${task.name} (${course.name})`, select(
                        user['task-status'][taskId] || 'pending',
                        ['pending', 'submitted', 'completed'],
                        (value) => {
                            if (value === 'pending') delete user['task-status'][taskId];
                            else user['task-status'][taskId] = value;
                        },
                    )));
                });
            });
            card.append(button('Remove user', 'btn-outline-danger', () => {state.users.users.splice(index, 1); rerender();}));
            return card;
        };
        const validate = () => {
            const errors = [];
            const courseIds = new Set();
            const taskIds = new Set();
            state.courses.courses.forEach((course, courseIndex) => {
                const courseId = slug(course.name);
                if (!courseId) errors.push(`Course ${courseIndex + 1} needs a name.`);
                if (courseIds.has(courseId)) errors.push(`Course ID collision: ${courseId}.`);
                courseIds.add(courseId);
                (course.tasks || []).forEach((task, taskIndex) => {
                    const taskId = `${courseId}.${slug(task.name)}`;
                    if (!slug(task.name)) errors.push(`Task ${taskIndex + 1} in ${course.name} needs a name.`);
                    if (taskIds.has(taskId)) errors.push(`Task ID collision: ${taskId}.`);
                    taskIds.add(taskId);
                });
            });
            const userIds = new Set();
            state.users.users.forEach((user, userIndex) => {
                const userId = slug(user.name);
                if (!userId) errors.push(`User ${userIndex + 1} needs a name.`);
                if (userIds.has(userId)) errors.push(`Username collision: ${userId}.`);
                userIds.add(userId);
                if (user.role === 'student' && !(user.class || '').trim()) {
                    errors.push(`${user.name || `User ${userIndex + 1}`} needs a class.`);
                }
                if (!(user.courses || []).length) errors.push(`${user.name || `User ${userIndex + 1}`} needs a course.`);
                (user.courses || []).filter((id) => !courseIds.has(id)).forEach((id) => {
                    errors.push(`${user.name} references unknown course ${id}.`);
                });
                Object.keys(user['task-status'] || {}).filter((id) => !taskIds.has(id)).forEach((id) => {
                    errors.push(`${user.name} references unknown task ${id}.`);
                });
            });
            if (!state.users.password) errors.push('The shared password is required.');
            return errors;
        };
        const save = async() => {
            try {
                const errors = validate();
                if (errors.length) {
                    state.status = {state: 'invalid', errors};
                    rerender();
                    return;
                }
                const response = await fetch(`save.php?sesskey=${encodeURIComponent(sesskey)}`, {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({courses: state.courses, users: state.users}),
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || response.statusText);
                state.status = {state: 'queued', hash: payload.result.hash};
                rerender();
            } catch (error) {
                state.status = {state: 'failed', error: error.message}; rerender();
            }
        };
        setInterval(async() => {
            try {
                state.status = await (await fetch('status.php')).json();
                const panel = root.querySelector('[data-edudemo-status]');
                if (panel) {
                    panel.className = `alert ${state.status.state === 'ready' ? 'alert-success' : 'alert-info'}`;
                    panel.textContent = JSON.stringify(state.status, null, 2);
                }
            } catch (error) {}
        }, 3000);
        rerender();
    };
    return {init};
});
