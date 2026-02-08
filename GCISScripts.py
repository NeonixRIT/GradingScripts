import os
import shutil

from tuiframeworkpy import (
    Dependency,
    ConfigEntry,
    TUI,
    find_option_by_prefix_text,
    LIGHT_RED,
    WHITE,
)

from tuiframeworkpy.model.utils import BareGitHubAPIClient

from view import (
    MainMenu,
    CloneMenu,
    PresetsMenu,
    ConfigMenu,
    SelectCSVMenu,
    AddMenu,
    CloneHistoryMenu,
    StudentParamsMenu,
)

VERSION = '2.6.2'


# def verify_token_org(config) -> set:
#     invalid_fields = set()
#     try:
#         tmp_client = BareGitHubAPIClient()
#         authorized, resp_code = tmp_client.is_authorized(config.organization, config.github_token)
#         if resp_code == 200 and authorized:
#             return invalid_fields
#         elif resp_code == 401:
#             invalid_fields.add('github_token')
#         elif resp_code == 404:
#             invalid_fields.add('organization')
#     except ConnectionError as e:
#         print(f'{LIGHT_RED}FATAL: Unable to contact GitHub API.{WHITE}')
#         raise e
#     return invalid_fields


def verify_presets(config) -> set:
    invalid_fields = set()
    for preset in config.presets:
        if not isinstance(preset[-1], list) and len(preset) < 6:
            preset.append([0, 0, 0])
        if not isinstance(preset[-1], str) and len(preset) < 7:
            preset.append('GitHub')
    return invalid_fields

def verify_github_conf(config) -> set:
    invalid_fields = set()
    if (not config.github_token or not config.github_organization) and config.default_clone_source == 'GitHub':
        print(f'{LIGHT_RED}WARNING: GitHub token and organization are required if using GitHub as default clone source.{WHITE}')
        invalid_fields.add('github_token')
    return invalid_fields

def verify_gitlab_conf(config) -> set:
    invalid_fields = set()
    if (not config.gitlab_token or not config.gitlab_organization or not config.gitlab_server) and config.default_clone_source == 'GitLab':
        print(f'{LIGHT_RED}WARNING: GitLab token, organization, and server are required if using GitLab as default clone source.{WHITE}')
        invalid_fields.add('gitlab_token')
    if (config.gitlab_server and not config.gitlab_server.startswith('http')):
        print(f'{LIGHT_RED}WARNING: GitLab server URL expected to start with http or https.{WHITE}')
        invalid_fields.add('gitlab_server')
    if config.gitlab_server.endswith('/'):
        config.gitlab_server = config.gitlab_server[:-1]
    return invalid_fields

def set_csv_values(context, entry, prompt_func):
    if len(os.listdir('./data/csvs/')) == 0:
        context.config_manager.set_config_value(entry.name, prompt_func())
        return
    select_csv_menu = SelectCSVMenu(21, context)
    select_csv_menu.run()
    student_csv_menu_quit = select_csv_menu.student_csv_menu_quit

    if student_csv_menu_quit:
        context.config_manager.set_config_value(entry.name, prompt_func())


def set_student_params(context, entry, prompt_func):
    student_param_menu = StudentParamsMenu(22, context)
    student_param_menu.run()


def get_application_folder():
    import pathlib
    import sys

    path = ''

    home = pathlib.Path.home()

    if sys.platform == 'win32':
        path = home / 'AppData/Roaming'
    elif sys.platform == 'linux':
        path = home / '.local/share'
    elif sys.platform == 'darwin':
        path = home / 'Library/Application Support'

    return path / 'GCISGradingScripts'


def main():
    # Get application folder path
    # This is where the update script is copied to
    app_folder = get_application_folder()

    # Enable Color if using Windows
    if os.name == 'nt':
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    # Define Dependencies
    git = Dependency('git', '2.30', '')  # clone repoes with cli
    niquests = Dependency('niquests', '3.12.0', 'pip')  # http client
    orjson = Dependency('orjson', '3.10.0', 'pip')  # fast json parser

    # Platform dependent dependency
    # fast_evenloop = Dependency('uvloop', '0.21.0', 'pip') if os.name != 'nt' else Dependency('winloop', '0.1.8', 'pip')

    # Define Config Entries
    default_clone_source = ConfigEntry(
        'default_clone_source',
        'Default Clone Source',
        'GitHub',
        'Default Clone Source (GitHub or GitLab): ',
        prompt=True,
        is_multichoice_prompt=True,
        multichoice_options=['GitHub', 'GitLab'],
    )
    gitlab_token_entry = ConfigEntry(
        'gitlab_token',
        'GitLab Token',
        None,
        'GitLab Authentication Token (enter to skip): ',
        prompt=True,
        censor=True,
    )
    github_token_entry = ConfigEntry(
        'github_token',
        'GitHub Token',
        None,
        'GitHub Authentication Token (enter to skip): ',
        prompt=True,
        censor=True,
    )
    github_org_entry = ConfigEntry('github_organization', 'GitHub Organization', None, 'GitHub Organization Name (enter to skip): ', prompt=True)
    gitlab_org_entry = ConfigEntry('gitlab_organization', 'GitLab Organization', None, 'GitLab Organization Name (enter to skip): ', prompt=True)
    gitlab_server_entry = ConfigEntry('gitlab_server', 'GitLab Server', None, 'GitLab Server (enter to skip): ', prompt=True)
    students_csv = ConfigEntry(
        'students_csv',
        'Students CSV Path',
        None,
        'Enter path of csv file containing username and name of students: ',
        prompt=True,
        is_path=True,
    )
    out_dir_entry = ConfigEntry(
        'out_dir',
        'Output Folder',
        '.',
        'Output directory for assignment files (`enter` for current directory): ',
        prompt=True,
        is_path=True,
    )
    replace_clone_duplicates = ConfigEntry(
        'replace_clone_duplicates',
        'Replace Duplicate Output Folder',
        True,
        'Replace content in output directory instead of changing name?',
        prompt=True,
        is_bool_prompt=True,
    )
    presets = ConfigEntry('presets', 'Presets', [], None, prompt=False)
    clone_history = ConfigEntry('clone_history', 'Clone History', [], None, prompt=False)
    student_params = ConfigEntry('extra_student_parameters', 'Extra Student Parameters', [], None, prompt=False)
    gitlab_path_to_repos = ConfigEntry(
        'gitlab_path_to_repos',
        'Gitlab path to repos',
        'students',
        'Subpath to repos: ',
        prompt=True,
    )
    config_entries = [
        default_clone_source,
        gitlab_token_entry,
        github_token_entry,
        github_org_entry,
        gitlab_org_entry,
        gitlab_server_entry,
        students_csv,
        out_dir_entry,
        replace_clone_duplicates,
        presets,
        clone_history,
        student_params,
        gitlab_path_to_repos,
    ]

    # Define Default Folders
    default_paths = ['./data', './data/csvs', './data/files_to_add', str(app_folder)]

    # Create TUI
    tui = TUI(VERSION, [git, orjson, niquests], 'data/config.json', config_entries, default_paths)

    # Register Custom Verify Methods
    # tui.context.config_manager += verify_token_org
    tui.context.config_manager += verify_github_conf
    tui.context.config_manager += verify_gitlab_conf
    tui.context.config_manager += verify_presets

    # Define Main Menu
    main_menu = MainMenu(0, VERSION)
    tui.add_menu(main_menu)

    # Define Submenus
    clone_menu = CloneMenu(10)  # clone menu
    tui.add_submenu(clone_menu, main_menu)

    preset_menu = PresetsMenu(11)  # submenu of clone menu
    tui.add_submenu(preset_menu, clone_menu)

    clone_history_menu = CloneHistoryMenu(12)  # submenu of clone menu
    tui.add_submenu(clone_history_menu, clone_menu)

    add_menu = AddMenu(20)  # add menu
    tui.add_submenu(add_menu, main_menu)

    # Define Edit Config Menu
    custom_edit_fields = {
        'students_csv': set_csv_values,
        'extra_student_parameters': set_student_params,
    }
    config_menu = ConfigMenu(99, custom_edit_fields)
    tui.add_submenu(config_menu, main_menu)

    # Setup Menu Options That Open Submenus
    main_menu.options[1].on_select += lambda: tui.open_menu(clone_menu.id)
    find_option_by_prefix_text(clone_menu, 'Manage Presets').on_select += lambda: tui.open_menu(preset_menu.id)
    find_option_by_prefix_text(clone_menu, 'Clone History').on_select += lambda: tui.open_menu(clone_history_menu.id)
    main_menu.options[3].on_select += lambda: tui.open_menu(config_menu.id)
    main_menu.options[2].on_select += add_menu.run

    # Copy update script to path
    if (app_folder / 'update.py').exists():
        os.remove(app_folder / 'update.py')
    shutil.copy('./utils/update.py', app_folder / 'update.py')

    # Run TUI
    tui.start()


if __name__ == '__main__':
    main()
