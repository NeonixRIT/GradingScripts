import asyncio
import shutil
import os

from .clone_preset import ClonePreset

from utils import get_color_from_bool, run, list_to_multi_clone_presets
from tuiframeworkpy import SubMenu, Event, MenuOption
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, WHITE

# Get computer's current UTC offset
# Then get the inverse so that when due date/time is input in local time, it will be processed as UTC
LOG_FILE_PATH = './data/logs.log'


class CloneMenu(SubMenu):
    __slots__ = ['client', 'local_options', 'preset_options', 'dry_run', 'parameters']

    def __init__(self, id):
        self.client = None
        self.local_options = []
        self.preset_options = []
        self.dry_run = False

        self.parameters = dict()

        manage_presets = MenuOption(1, 'Manage Presets', Event(), Event(), Event(), pause=False)
        manage_presets.on_exit += self.load
        self.local_options.append(manage_presets)

        toggle_dry_run_event = Event()
        toggle_dry_run_event += self.toggle_dry_run
        toggle_dry_run_event += self.load
        toggle_clone_tag = MenuOption(
            2,
            f'Dry Run: {get_color_from_bool(self.dry_run)}{self.dry_run}{WHITE}',
            toggle_dry_run_event,
            Event(),
            Event(),
            pause=False,
        )
        self.local_options.append(toggle_clone_tag)

        clone_history = MenuOption(3, 'Clone History', Event(), Event(), Event(), pause=False)
        clone_history.on_exit += self.load
        self.local_options.append(clone_history)

        clone_repos_event = Event()
        clone_repos_event += self.clone_repos
        clone_repos = MenuOption(4, 'Continue Without Preset', clone_repos_event, Event(), Event())
        self.local_options.append(clone_repos)

        SubMenu.__init__(
            self,
            id,
            'Clone Presets',
            self.preset_options + self.local_options,
            Event(),
            Event(),
            preload=False,
        )
        self.on_enter += self.load

    def load(self):
        self.client = self.parent.client

        self.preset_options = self.build_preset_options()
        for i, option in enumerate(self.local_options):
            option.number = len(self.preset_options) + i + 1
            if option.text.startswith('Dry Run: '):
                option.text = f'Dry Run: {get_color_from_bool(self.dry_run)}{self.dry_run}{WHITE}'
        options = self.preset_options + self.local_options
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'
        self.prompt_string = self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '

    def toggle_dry_run(self):
        self.dry_run = not self.dry_run

    def save_report(self, report):
        clone_logs = self.context.config_manager.config.clone_history
        clone_logs.append(report)
        if len(clone_logs) > 8:
            clone_logs = clone_logs[1:]
        self.context.config_manager.set_config_value('clone_history', clone_logs)

    def clone_repos(self, preset: ClonePreset = None):
        # import uvloop

        self.context.dry_run = bool(self.dry_run)
        # asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        asyncio.run(self.client.run(preset))
        del self.context.dry_run

    def build_preset_options(self) -> list:
        options = []
        for i, preset in enumerate(list_to_multi_clone_presets(self.context.config_manager.config.presets)):
            option_event = Event()

            def on_select(bound_preset=preset):
                self.clone_repos(bound_preset)

            option_event += on_select
            option = MenuOption(i + 1, preset.name, option_event, Event(), Event())
            options.append(option)
        return options


def attempt_get_tag():
    """
    Get due tag name from input. Does not accept empty input.
    """
    assignment_name = input('Tag Name: ')  # get assignment name (repo prefix)
    while not assignment_name:  # if input is empty ask again
        assignment_name = input('Please input an assignment name: ')
    return assignment_name


def onerror(func, path: str, exc_info) -> None:
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


class LocalRepo:
    """
    Object representing a cloned repo
    """

    __slots__ = ['__path', '__old_name', '__new_name', '__remote_repo']

    def __init__(self, path: str, old_name: str, new_name: str, remote_repo):
        self.__path = path
        self.__old_name = old_name
        self.__new_name = new_name
        self.__remote_repo = remote_repo

    def __str__(self) -> str:
        return self.__new_name

    def __repr__(self) -> str:
        return f'LocalRepo[path={self.__path}, old_name={self.__old_name}, new_name={self.__new_name}]'

    def old_name(self) -> str:
        return self.__old_name

    async def reset_to_remote(self):
        await run('git fetch --all')
        await run(f'git reset --hard origin/{self.__remote_repo.default_branch}')
        await run('git pull')

    async def attempt_git_workflow(self, commit_message: str):
        await run('git add *', self.__path)
        await run(f'git commit -m "{commit_message}"', self.__path)
        await run('git push', self.__path)

    async def get_commit_hash(self, date_due: str, time_due: str) -> str:
        """
        Get commit hash at timestamp and reset local repo to timestamp on the default branch
        """
        try:
            # run process on system that executes 'git rev-list' command. stdout is redirected so it doesn't output to end user
            cmd = f'git log --max-count=1 --date=local --before="{date_due.strip()} {time_due.strip()}" --format=%H'
            stdout, stderr = await run(cmd, self.__path)
            return stdout
        except Exception as e:
            print(f'{LIGHT_RED}[{self}] Get Commit Hash Failed: Likely accepted assignment after given date/time.{WHITE}')
            # await log_info('Get Commit Hash Failed', 'Likely accepted assignment after given date/time.', self, e)
            raise e

    async def rollback(self, commit_hash: str) -> bool:
        """
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        """
        try:
            # run process on system that executes 'git reset' command. stdout is redirected so it doesn't output to end user
            # git reset is similar to checkout but doesn't care about detached heads and is more forceful
            cmd = f'git reset --hard {commit_hash}'
            await run(cmd, self.__path)
            return True
        except Exception:
            print(f'{LIGHT_RED}[{self}] Rollback Failed: Likely invalid filename at commit `{commit_hash}`.{WHITE}')
            # await log_info('Rollback Failed', f'Likely invalid filename at commit `{commit_hash}`.', self, e)
            return False

    async def add(self, files_to_add: list[tuple[str, str, bool]], commit_message: str):
        await self.reset_to_remote()

        for path, filename, _ in files_to_add:
            if filename.endswith('.zip'):
                shutil.unpack_archive(path, f'{self.__path}/{filename[:-4]}')
                continue
            shutil.copy(path, self.__path)

        await self.attempt_git_workflow(commit_message)

    async def delete(self) -> None:
        shutil.rmtree(self.__path, onerror=onerror)

    async def get_stats(self) -> list:
        raise NotImplementedError('This method has not been implemented.')
