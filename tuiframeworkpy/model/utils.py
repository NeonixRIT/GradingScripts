import json
import os

from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE

from pathlib import Path
from types import SimpleNamespace

def clear():
    print("\033c\033[3J\033[2J\033[0m\033[H")


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


def is_windows() -> bool:
    return os.name == 'nt'


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


def find_option_by_prefix_text(menu, text_prefix):
    for _, option in menu.options.items():
        if option.text.startswith(text_prefix):
            return option
    return None
