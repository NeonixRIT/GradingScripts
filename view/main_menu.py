# from event import Event
# from menu import Menu
# from menu_option import MenuOption
# from submenu import SubMenu
import model

from .clone_menu import CloneMenu
from .config_menu import ConfigMenu
from .setup import setup
from .add_menu import AddMenu

from pathlib import Path

MAX_THREADS = 200
CONFIG_PATH = './data/config.json'
VERSION = '2.0.0'
PY_DEPENDENCIES = {'versionmanagerpy': '1.0.2', 'pygithub': '1.50'}
GIT_DEPENDENCY = '2.30.0'

def check_and_install_dependencies():
    for package, version in PY_DEPENDENCIES.items():
        installed, correct_version = model.utils.check_package(package, version)
        if not installed or not correct_version:
            model.utils.install_package(package, correct_version)

    installed, correct_version = model.utils.check_git(GIT_DEPENDENCY)
    if not installed or not correct_version:
        print(f'{model.colors.LIGHT_RED}FATAL: Git not installed correctly or is not at or above version 2.30.0{model.colors.WHITE}')


class MainMenu(model.Menu):
    __slots__ = ['config', 'client', 'repos', 'students']

    def __init__(self):
        setup_complete = Path(CONFIG_PATH).exists()
        check_and_install_dependencies()

        from versionmanagerpy import versionmanager
        vm = versionmanager.VersionManager('NeonixRIT', 'GradingScripts', VERSION)
        vm.on_outdated += lambda: print('outdated')
        update_status = vm.check_status()
        if update_status == versionmanager.Status.OUTDATED:
            model.utils.print_updates(VERSION)

        clone_repos_event = model.Event()
        clone_repos = model.MenuOption(1, 'Clone Repos', clone_repos_event, False, setup_complete)

        add_event = model.Event()
        add = model.MenuOption(2, 'Add Files', add_event, True, setup_complete)

        manage_repos_event = model.Event()
        manage_repos = model.MenuOption(3, 'Repo Manager', manage_repos_event, False, False)

        config_event = model.Event()
        config = model.MenuOption(4, 'Edit Config', config_event, False, setup_complete)

        if setup_complete:
            self.config = model.utils.read_config(CONFIG_PATH)
            from github import Github
            self.client = Github(self.config.token, pool_size=MAX_THREADS).get_organization(self.config.organization)
            self.repos = self.client.get_repos()
            self.students = model.repo_utils.get_students(self.config.students_csv)

            clone_menu = CloneMenu(self.config, self.client, self.repos, self.students)
            config_menu = ConfigMenu()

            clone_repos.on_select += clone_menu.run
            add.on_select += lambda: AddMenu(self.config)
            config.on_select += config_menu.run


        def update_options():
            old_setup_complete = setup_complete
            new_setup_complete = Path('./data/config.json').exists()

            if old_setup_complete != new_setup_complete and new_setup_complete:
                clone_repos.enabled = new_setup_complete
                add.enabled = new_setup_complete
                config.enabled = new_setup_complete

                self.config = model.utils.read_config(CONFIG_PATH)
                from github import Github
                self.client = Github(self.config.token, pool_size=MAX_THREADS).get_organization(self.config.organization)
                self.repos = self.client.get_repos()
                self.students = model.repo_utils.get_students(self.config.students_csv)

                clone_menu = CloneMenu(self.config, self.client, self.repos, self.students)
                config_menu = ConfigMenu()

                clone_repos.on_select += clone_menu.run
                add.on_select += lambda: AddMenu(self.config)
                config.on_select += config_menu.run

            if new_setup_complete:
                self.students = model.repo_utils.get_students(self.config.students_csv)


        setup_config_event = model.Event()
        setup_config_event += setup
        setup_config_event += update_options
        setup_config = model.MenuOption(5, 'Run Setup', setup_config_event)

        options = [clone_repos, add, manage_repos, config, setup_config]
        model.Menu.__init__(self, f'GCIS Grading Scripts {model.utils.get_color_from_status(update_status)}v{VERSION}{model.colors.WHITE}', options)
