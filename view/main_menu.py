from utils import get_color_from_status

from tuiframeworkpy import Menu, Event, MenuOption
from tuiframeworkpy import LIGHT_GREEN, LIGHT_RED, WHITE

from .github_client import GitHubAPIClient

MAX_THREADS = 200


class MainMenu(Menu):
    __slots__ = ['client', '__version']

    def __init__(self, id, version):
        clone_repos = MenuOption(1, 'Clone Repos', Event(), Event(), Event(), pause=False)
        add = MenuOption(2, 'Add Files', Event(), Event(), Event(), pause=True)
        manage_repos = MenuOption(3, 'Repo Manager', Event(), Event(), Event(), pause=False, enabled=False)
        config = MenuOption(4, 'Edit Config', Event(), Event(), Event(), pause=False)

        options = [clone_repos, add, manage_repos, config]
        Menu.__init__(self, id, f'GCIS Grading Scripts {LIGHT_GREEN}v{version}{WHITE}', options)

        self.client = None

        self.__version = version

    def load(self):
        self.name = f'GCIS Grading Scripts {get_color_from_status(self.context.update_status)}v{self.__version}{WHITE}'
        try:
            self.client = GitHubAPIClient(
                self.context,
                self.context.config_manager.config.token,
                self.context.config_manager.config.organization,
            )
            authorized, resp_code = self.client.is_authorized()
            if not authorized:
                print(f'{LIGHT_RED}FATAL: GitHub API Authorization failed. Make sure your token is valid and has the correct permissions.\nResponse Code: {resp_code}{WHITE}')
                raise ValueError(f'GitHub API Authorization failed. Make sure your token is valid and has the correct permissions.\nResponse Code: {resp_code}')
            if resp_code != 200:
                print(f'{LIGHT_RED}FATAL: GitHub API returned an unexpected response code. Perhaphs try again later.\nResponse Code: {resp_code}{WHITE}')
                raise ValueError(f'GitHub API returned an unexpected response code. Perhaphs try again later.\nResponse Code: {resp_code}')
        except ConnectionError as e:
            print(f'{LIGHT_RED}FATAL: Unable to contact GitHub API.{WHITE}')
            raise e
