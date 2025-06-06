import json
import os
import pathlib
import re
import sys

from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE

from types import SimpleNamespace
from urllib.parse import urlencode


def get_page_by_rel(links: str, rel: str = 'last'):
    for token in links.split(', '):
        if f'rel="{rel}"' not in token:
            continue
        val = re.findall(r'[&?]page=(\d+).*>;', links)
        if val:
            return int(val[0])
    return None


class BareGitHubAPIClient:
    def __init__(self) -> None:
        self.headers = {
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }

    def is_authorized(self, organization: str, token: str):
        import niquests
        import orjson as jsonbackend

        self.headers['Authorization'] = f'token {token}'
        org_url = f'https://api.github.com/orgs/{organization}'
        try:
            response = niquests.get(org_url, headers=self.headers, timeout=10)
            org_auth = jsonbackend.loads(response.content).get('total_private_repos', False)
            if not org_auth:
                return False, response.status_code
        except TimeoutError:
            raise ConnectionError('Connection timed out.') from None
        return True, response.status_code


def get_application_folder():
    path = ''

    home = pathlib.Path.home()

    if sys.platform == 'win32':
        path = home / 'AppData/Roaming'
    elif sys.platform == 'linux':
        path = home / '.local/share'
    elif sys.platform == 'darwin':
        path = home / 'Library/Application Support'

    return path / 'GCISGradingScripts'


def update(latest_version, cwd):
    python_path = sys.executable
    os.execl(
        python_path,
        python_path,
        get_application_folder() / 'update.py',
        latest_version,
        cwd,
    )


def clear():
    print('\n' * 100)
    print('\033c\033[3J\033[2J\033[0m\033[H' * 200)
    os.system('cls' if os.name == 'nt' else 'clear')


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


def bool_prompt(prompt: str, default_output: bool) -> bool:
    y_str = 'Y' if default_output else 'y'
    n_str = 'N' if not default_output else 'n'
    result = input(f'{prompt} ({LIGHT_GREEN}{y_str}{WHITE}/{LIGHT_RED}{n_str}{WHITE}): ')
    return default_output if not result else True if result.lower() == 'y' else False if result.lower() == 'n' else default_output


def print_updates(current_version: str, tui_instance):
    client = BareGitHubAPIClient()
    repo = client.get_repo('NeonixRIT', 'GradingScripts')
    releases = client.get_releases(repo)
    print_release_changes_since_update(releases, current_version)
    # input('Press enter to continue...')
    res = bool_prompt('Do you wish to update now?', True)
    if res:
        update(list(releases)[0].tag_name, os.getcwd())
        tui_instance.update_instance = True


def make_new_config() -> SimpleNamespace:
    token = input('Github Authentication Token: ')
    organization = input('Organization Name: ')
    student_filename = input('Enter path of csv file containing username and name of students: ')
    output_dir = pathlib.Path(input('Output directory for assignment files (`enter` for current directory): '))
    if not output_dir:
        output_dir = pathlib.Path.cwd()
    while not pathlib.Path.is_dir(output_dir):
        print(f'Directory `{output_dir}` not found.')
        output_dir = pathlib.Path(input('Output directory for assignment files (`enter` for current directory): '))

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
