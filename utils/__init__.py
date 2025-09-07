import asyncio
import json
import os
import re
import subprocess

from tuiframeworkpy import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE

from view.clone_preset import ClonePreset

from pathlib import Path
from types import SimpleNamespace


def onerror(func, path: str, exc_info) -> None:
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def clear():
    print('\n' * 100)
    print('\033c\033[3J\033[2J\033[0m\033[H' * 200)
    os.system('cls' if os.name == 'nt' else 'clear')


def censor_string(string: str) -> str | None:
    if len(string) <= 7:
        return
    return ('*' * int(len(string) - len(string) / 5)) + string[-int(len(string) / 5) :]


def bool_prompt(prompt: str, default_output: bool) -> bool:
    y_str = 'Y' if default_output else 'y'
    n_str = 'N' if not default_output else 'n'
    result = input(f'{prompt} ({LIGHT_GREEN}{y_str}{WHITE}/{LIGHT_RED}{n_str}{WHITE}): ')
    return default_output if not result else True if result.lower() == 'y' else False if result.lower() == 'n' else default_output


def multichoice_prompt(prompt: str, options: list, default_index: int):
    options_str = '\n'.join([f'[{i + 1}] {LIGHT_GREEN}{opt}{WHITE}' if i == default_index else f'[{i + 1}] {opt}' for i, opt in enumerate(options)])
    print(f'Choose one of the following options:\n{options_str}')
    while True:
        result = input(f'{prompt}')
        if not result:
            return options[default_index]
        if result.isdigit() and (1 <= int(result) <= len(options)):
            return options[int(result) - 1]
        print(f'{LIGHT_RED}Invalid option. Please choose one of the options above.{WHITE}')


def get_color_from_status(status) -> str:
    import versionmanagerpy

    if status == versionmanagerpy.versionmanager.Status.OUTDATED:
        return LIGHT_RED
    elif status == versionmanagerpy.versionmanager.Status.CURRENT:
        return LIGHT_GREEN
    elif status == versionmanagerpy.versionmanager.Status.DEV:
        return CYAN
    return LIGHT_GREEN


def print_release_changes_since_update(releases, current_version) -> None:
    from versionmanagerpy import version

    current_version = version.Version(current_version)
    print(f'{LIGHT_GREEN}An upadate is available. {current_version} -> {releases[0].tag_name}{WHITE}')
    for release in list(releases)[::-1]:
        release_version = version.Version(release.tag_name)
        if release_version > current_version:
            print(f'{LIGHT_GREEN}Version: {release_version}\nDescription:\n{release.body}\n{WHITE}')


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

    values = {
        'token': token,
        'organization': organization,
        'students_csv': student_filename,
        'out_dir': str(output_dir),
        'presets': [],
        'add_rollback': [],
    }
    values_formatted = json.dumps(values, indent=4)
    return json.loads(values_formatted, object_hook=lambda d: SimpleNamespace(**d))


def is_windows() -> bool:
    return os.name == 'nt'


REQ_CONFIG_FIELDS = {
    'token': None,
    'organization': None,
    'students_csv': None,
    'out_dir': '.',
    'presets': [],
    'add_rollback': [],
}


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


def run_cmd(cmd: str | list, cwd=None) -> tuple[str | None, str | None]:
    """
    Syncronously start a subprocess and run a command returning its output
    """
    if cwd is None:
        cwd = os.getcwd()
    proc = subprocess.Popen(cmd, cwd=cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    stdout, stderr = proc.communicate()
    return (stdout.decode().strip() if stdout else None, stderr.decode().strip() if stderr else None, proc.returncode)


async def async_run_cmd(cmd: str | list, cwd=None) -> tuple[str | None, str | None]:
    """
    Asyncronously start a subprocess and run a command returning its output
    """
    if cwd is None:
        cwd = os.getcwd()
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    return (stdout.decode().strip() if stdout else None, stderr.decode().strip() if stderr else None, proc.returncode)


def list_to_clone_preset(args: list) -> ClonePreset | None:
    if len(args) != 7:
        return
    return ClonePreset(args[0], args[1], args[2], args[3], args[4], args[5], args[6])


def list_to_multi_clone_presets(presets: list) -> list:
    return [list_to_clone_preset(preset_list) for preset_list in presets]


def check_time(time_inp: str):
    """
    Ensure proper 24hr time format
    """
    if not re.match(r'\d{2}:\d{2}', time_inp):
        return False
    return True
