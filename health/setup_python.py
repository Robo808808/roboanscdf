---
- name: Setup
Python
Environment
for Oracle User
    hosts: oracle_servers
    become: no  # Important: we're not using root
    remote_user: oracle

    vars:
    python_version: "3.10.12"  # A modern Python 3.8+ version
    virtualenv_name: "oracle_env"
    pyenv_root: "{{ ansible_env.HOME }}/.pyenv"
    pyenv_path: "{{ pyenv_root }}/bin:{{ pyenv_root }}/shims:{{ ansible_env.PATH }}"
    oracledb_packages:
    - oracledb
    # Add any other Python packages you need

tasks:
- name: Install
pyenv
prerequisites
ansible.builtin.package:
name:
- make
- build - essential
- libssl - dev
- zlib1g - dev
- libbz2 - dev
- libreadline - dev
- libsqlite3 - dev
- wget
- curl
- llvm
- libncurses5 - dev
- xz - utils
- tk - dev
- libxml2 - dev
- libxmlsec1 - dev
- libffi - dev
- liblzma - dev
state: present
become: yes  # Only this task requires root to install system dependencies

- name: Check if pyenv is installed
ansible.builtin.stat:
path: "{{ pyenv_root }}/bin/pyenv"
register: pyenv_binary

- name: Clone
pyenv
repository
ansible.builtin.git:
repo: https: // github.com / pyenv / pyenv.git
dest: "{{ pyenv_root }}"
update: no
when: not pyenv_binary.stat.exists

- name: Add
pyenv
to.bashrc
ansible.builtin.blockinfile:
path: "{{ ansible_env.HOME }}/.bashrc"
block: |
export
PYENV_ROOT = "{{ pyenv_root }}"
export
PATH = "{{ pyenv_path }}"
eval
"$(pyenv init -)"
marker: "# {mark} ANSIBLE MANAGED BLOCK - PYENV"
create: yes

- name: Check if Python
version is installed
ansible.builtin.shell: |
export
PYENV_ROOT = "{{ pyenv_root }}"
export
PATH = "{{ pyenv_path }}"
eval
"$(pyenv init -)"
pyenv
versions | grep
{{python_version}}
register: pyenv_version_check
changed_when: false
failed_when: false

- name: Install
Python
version
ansible.builtin.shell: |
export
PYENV_ROOT = "{{ pyenv_root }}"
export
PATH = "{{ pyenv_path }}"
eval
"$(pyenv init -)"
pyenv
install
{{python_version}}
when: pyenv_version_check.rc != 0

- name: Create
virtualenv
directory
ansible.builtin.file:
path: "{{ ansible_env.HOME }}/.virtualenvs"
state: directory
mode: '0755'

- name: Check if virtualenv
exists
ansible.builtin.stat:
path: "{{ ansible_env.HOME }}/.virtualenvs/{{ virtualenv_name }}"
register: virtualenv_dir

- name: Create
Python
virtualenv
ansible.builtin.shell: |
export
PYENV_ROOT = "{{ pyenv_root }}"
export
PATH = "{{ pyenv_path }}"
eval
"$(pyenv init -)"
python - m
venv
{{ansible_env.HOME}} /.virtualenvs / {{virtualenv_name}}
environment:
PYENV_VERSION: "{{ python_version }}"
when: not virtualenv_dir.stat.exists

- name: Install
pip
packages in virtualenv
ansible.builtin.pip:
name: "{{ oracledb_packages }}"
virtualenv: "{{ ansible_env.HOME }}/.virtualenvs/{{ virtualenv_name }}"
state: present

- name: Create
activation
script
ansible.builtin.copy:
dest: "{{ ansible_env.HOME }}/activate_oracle_env.sh"
content: |
# !/bin/bash
export
PYENV_ROOT = "{{ pyenv_root }}"
export
PATH = "{{ pyenv_path }}"
eval
"$(pyenv init -)"
source
{{ansible_env.HOME}} /.virtualenvs / {{virtualenv_name}} / bin / activate
echo
"Oracle Python environment activated. You can now use the oracledb package."
mode: '0755'