from utils import get_color_from_status

from tuiframeworkpy import Menu, Event, MenuOption
from tuiframeworkpy import LIGHT_GREEN, LIGHT_RED, WHITE

from .clone_menu import get_students

MAX_THREADS = 200
VERSION = '2.0.4'

class MainMenu(Menu):
    __slots__ = ['client', 'repos', 'students']

    def __init__(self, id):
        clone_repos = MenuOption(1, 'Clone Repos', Event(), Event(), Event(), pause=False)
        add = MenuOption(2, 'Add Files', Event(), Event(), Event(), pause=True)
        manage_repos = MenuOption(3, 'Repo Manager', Event(), Event(), Event(), pause=False, enabled=False)
        config = MenuOption(4, 'Edit Config', Event(), Event(), Event(), pause=False)

        options = [clone_repos, add, manage_repos, config]
        Menu.__init__(self, id, f'GCIS Grading Scripts {LIGHT_GREEN}v{VERSION}{WHITE}', options)

        self.client = None
        self.repos = None
        self.students = None

    def load(self):
        from github import Github
        self.name = f'GCIS Grading Scripts {get_color_from_status(self.context.update_status)}v{VERSION}{WHITE}'
        try:
            self.client = Github(self.context.config_manager.config.token, pool_size=MAX_THREADS).get_organization(self.context.config_manager.config.organization)
        except ConnectionError:
            print(f'{LIGHT_RED}FATAL: Unable to contact GitHub.{WHITE}')
            raise ConnectionError
        self.repos = self.client.get_repos()
        self.students = get_students(self.context.config_manager.config.students_csv)
