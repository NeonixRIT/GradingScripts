import ast
import itertools
import json
import os
import subprocess
import sys

from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .clone_preset import ClonePreset
from .repo_utils import get_repos, attempt_get_assignment

from pathlib import Path
from types import SimpleNamespace

def clear():
    print("\033c\033[3J\033[2J\033[0m\033[H")


def install_package(package: str, upgrade: bool = False):
    args = [sys.executable, '-m', 'pip', 'install', package]
    if upgrade:
        args.append('--upgrade')

    try:
        subprocess.check_call(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        pass # TODO raise custom exception


def check_package(req_package: str, req_version: str) -> bool:
    try:
        current_version = subprocess.check_output([sys.executable, '-m', 'pip', 'show', req_package], stderr=subprocess.PIPE).decode().split('\n')[1].split(': ')[1].strip()
        from versionmanagerpy import version
        if version.Version(current_version) > version.Version(req_version) or version.Version(current_version) == version.Version(req_version):
            return (True, True)
        return (True, False)
    except (subprocess.CalledProcessError, IndexError):
        return (False, False)


def check_git(req_version: str) -> tuple[bool, bool]:
    try:
        current_version = subprocess.check_output(['git', '--version'], stderr=subprocess.PIPE).decode().split(' ')[2][:6].strip()
        from versionmanagerpy import version
        if version.Version(current_version) > version.Version(req_version) or version.Version(current_version) == version.Version(req_version):
            return (True, True)
        return (True, False)
    except (subprocess.CalledProcessError, IndexError):
        return (False, False)


def get_color_from_status(status) -> str:
    import versionmanagerpy
    if status == versionmanagerpy.versionmanager.Status.OUTDATED:
        return LIGHT_RED
    elif status == versionmanagerpy.versionmanager.Status.CURRENT:
        return LIGHT_GREEN
    elif status == versionmanagerpy.versionmanager.Status.DEV:
        return CYAN
    return None


def print_release_changes_since_update(releases, current_version) -> None:
    from versionmanagerpy import version
    current_version = version.Version(current_version)
    print(f'{LIGHT_GREEN}An upadate is available. {current_version} -> {releases[0].tag_name}{WHITE}')
    for release in list(releases)[::-1]:
        release_version = version.Version(release.tag_name)
        if release_version > current_version:
            print(f'{LIGHT_GREEN}Version: {release_version}\nDescription:\n{release.body}\n{WHITE}')


def print_updates(current_version: str):
    from github import Github
    client = Github()
    repo = client.get_repo('NeonixRIT/GradingScripts')
    releases = repo.get_releases()
    print_release_changes_since_update(releases, current_version)
    input('Press enter to continue...')


def read_config(path_to_config: str) -> SimpleNamespace:
    config = json.loads(Path(path_to_config).read_text(), object_hook=lambda d: SimpleNamespace(**d))
    verify_config(config)
    return config


def save_config(config: SimpleNamespace):
    verify_config(config)
    config_str = json.dumps(config.__dict__, indent=4)

    if not Path('./data').exists():
        os.mkdir('./data')

    with open('./data/config.json', 'w') as f:
        f.write(config_str)
        f.flush()


def make_new_config() -> SimpleNamespace:
    token = input('Github Authentication Token: ')
    organization = input('Organization Name: ')
    student_filename = input('Enter path of csv file containing username and name of students: ')
    output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))
    if not output_dir:
        output_dir = Path.cwd()
    while not Path.is_dir(output_dir):
        print(f'Directory `{output_dir}` not found.')
        output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))

    values = {'token': token, 'organization': organization, 'students_csv': student_filename, 'out_dir': str(output_dir), 'presets': [], 'add_rollback': []}
    values_formatted = json.dumps(values, indent=4)
    return json.loads(values_formatted, object_hook=lambda d: SimpleNamespace(**d))


def censor_string(string: str) -> str:
    if len(string) <= 7:
        return
    return ('*' * int(len(string) - len(string) / 5)) + string[-int(len(string) / 5):]


def list_to_clone_preset(args: list) -> ClonePreset:
    if len(args) != 5:
        return
    return ClonePreset(args[0], args[1], args[2], args[3], args[4])


def list_to_multi_clone_presets(presets: list) -> list:
    return [list_to_clone_preset(preset_list) for preset_list in presets]


def is_windows() -> bool:
    return os.name == 'nt'


def verify_token_org(config: SimpleNamespace) -> set:
    invalid_fields = set()
    from github import Github, BadCredentialsException, UnknownObjectException
    try:
        Github(config.token).get_organization(config.organization)
    except BadCredentialsException:
        invalid_fields.add('token')
    except UnknownObjectException:
        invalid_fields.add('organization')
    return invalid_fields


def verify_paths(config: SimpleNamespace) -> set:
    invalid_fields = set()
    if not Path(config.students_csv).exists():
        invalid_fields.add('students_csv')
    if not Path(config.out_dir).exists():
        try:
            os.mkdir(config.out_dir)
        except PermissionError:
            invalid_fields.add('out_dir')
    return invalid_fields


REQ_CONFIG_FIELDS = {'token': None, 'organization': None, 'students_csv': None, 'out_dir': '.', 'presets': [], 'add_rollback': []}
def verify_config(config: SimpleNamespace):
    missing_fields = set()
    for required_field in REQ_CONFIG_FIELDS:
        if getattr(config, required_field, None) is None:
            if REQ_CONFIG_FIELDS[required_field] is None:
                missing_fields.add(required_field)
            else:
                setattr(config, required_field, REQ_CONFIG_FIELDS[required_field])

    invalid_fields = verify_token_org(config) or verify_paths(config) or missing_fields
    if len(invalid_fields) > 0:
        print(f'{LIGHT_RED}WARNING: Some values in your config seem to be missing or invalid. Please enter their fixed values.{WHITE}')
    for field in invalid_fields:
        new_value = input(f'Enter new [{field}] value: ')
        setattr(config, field, new_value)

    if len(invalid_fields) > 0:
        save_config(config)


def peek(iterable):
    try:
        first = next(iterable)
    except StopIteration:
        return None
    return itertools.chain([first], iterable)


def verify_assignment_name(assignment_name, org_repos):
    repos = peek(get_repos(assignment_name, org_repos))
    while repos is None or assignment_name == '':
        print(f'{LIGHT_RED}WARNING: There are no repos for that assignment. Enter a valid assignment name.{WHITE}')
        assignment_name = input('Assignment Name: ')
        repos = peek(get_repos(assignment_name, org_repos))
    return assignment_name, repos


def check_preset_names(config, name):
    for preset in list_to_multi_clone_presets(config.presets):
        if preset.name == name:
            return True
    return False


def walklevel(some_dir, level=1):
    some_dir = some_dir.rstrip(os.path.sep)
    if not os.path.isdir(some_dir):
        return None
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]


def get_color_from_bool(boolean):
    return LIGHT_GREEN if boolean else LIGHT_RED
