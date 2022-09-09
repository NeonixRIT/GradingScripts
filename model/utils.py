import json
import os
import subprocess
import sys

from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE

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
    return json.loads(Path(path_to_config).read_text(), object_hook=lambda d: SimpleNamespace(**d))


def save_config(config: SimpleNamespace):
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
