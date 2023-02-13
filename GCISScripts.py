import os
import shutil

from datetime import datetime

from tuiframeworkpy import Dependency, ConfigEntry, TUI, find_option_by_prefix_text, LIGHT_RED, WHITE

from view import MainMenu, CloneMenu, PresetsMenu, ConfigMenu, SelectCSVMenu, AddMenu, CloneHistoryMenu, StudentParamsMenu

VERSION = '2.1.6'


def verify_token_org(config) -> set:
    invalid_fields = set()
    from github import Github, BadCredentialsException, UnknownObjectException
    try:
        Github(config.token).get_organization(config.organization)
    except BadCredentialsException:
        invalid_fields.add('token')
    except UnknownObjectException:
        invalid_fields.add('organization')
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


def repos_cloned(self, number: int):
    self.send(f'CLONED {number}')


def clone_time(self, seconds: float):
    self.send(f'CLONETIME {seconds}')


def files_added(self, number: int):
    self.send(f'ADD {number}')


def add_time(self, seconds: float):
    self.send(f'ADDTIME {seconds}')


def students_accepted(self, number: int):
    month = datetime.now().strftime("%B").lower()
    self.send(f'ACCEPTED {month} {number}')


def get_application_folder():
    import pathlib
    import sys

    path = ''

    home = pathlib.Path.home()

    if sys.platform == "win32":
        path = home / "AppData/Roaming"
    elif sys.platform == "linux":
        path = home / ".local/share"
    elif sys.platform == "darwin":
        path = home / "Library/Application Support"

    return path / 'GCISGradingScripts'


def main():
    # Get application folder path
    app_folder = get_application_folder()

    # Enable Color if using Windows
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    # Define Dependencies
    pygithub = Dependency('pygithub', '1.50', 'pip', version_regex=r'(\d+\.\d+)')
    git = Dependency('git', '2.30', '')

    # Define Config Entries
    token_entry = ConfigEntry('token', 'Token', None, 'Github Authentication Token: ', prompt=True, censor=True)
    org_entry = ConfigEntry('organization', 'Organization', None, 'Organization Name: ', prompt=True)
    students_csv = ConfigEntry('students_csv', 'Students CSV Path', None, 'Enter path of csv file containing username and name of students: ', prompt=True, is_path=True)
    out_dir_entry = ConfigEntry('out_dir', 'Output Folder', '.', 'Output directory for assignment files (`enter` for current directory): ', prompt=True, is_path=True)
    presets = ConfigEntry('presets', 'Presets', [], None, prompt=False)
    clone_history = ConfigEntry('clone_history', 'Clone History', [], None, prompt=False)
    student_params = ConfigEntry('extra_student_parameters', 'Extra Student Parameters', [], None, prompt=True)
    config_entries = [token_entry, org_entry, students_csv, out_dir_entry, presets, clone_history, student_params]

    # Define Default Folders
    default_paths = ['./data', './data/csvs', './data/files_to_add', str(app_folder)]

    # Create TUI
    metrics_proxy_methods = [repos_cloned, clone_time, files_added, add_time, students_accepted]
    tui = TUI(VERSION, [pygithub, git], 'data/config.json', config_entries, 'www.neonix.me', 13370, metrics_proxy_methods, False, default_paths)

    # Add Custom Verify Methods
    tui.context.config_manager += verify_token_org

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
    custom_edit_fields = {'students_csv': set_csv_values, 'extra_student_parameters': set_student_params}
    config_menu = ConfigMenu(99, custom_edit_fields)
    tui.add_submenu(config_menu, main_menu)

    # Setup Menu Options That Open Submenus
    main_menu.options[1].on_select += lambda: tui.open_menu(clone_menu.id)
    find_option_by_prefix_text(clone_menu, 'Manage Presets').on_select += lambda: tui.open_menu(preset_menu.id)
    find_option_by_prefix_text(clone_menu, 'Clone History').on_select += lambda: tui.open_menu(clone_history_menu.id)
    main_menu.options[4].on_select += lambda: tui.open_menu(config_menu.id)
    main_menu.options[2].on_select += add_menu.run

    # Copy update script to path
    if (app_folder / 'update.py').exists():
        os.remove(app_folder / 'update.py')
    shutil.copy('./utils/update.py', app_folder / 'update.py')

    # Run TUI
    tui.start()


if __name__ == '__main__':
    main()
