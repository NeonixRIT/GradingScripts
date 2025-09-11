import csv
import re
import os
import shutil
import subprocess
import gc

from .clone_preset import ClonePreset
from .clone_report import CloneReport
from .student_param import StudentParam
from tuiframeworkpy import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE, YELLOW, MAGENTA
from utils import clear

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from urllib.parse import urlencode, quote

from pprint import pformat
from time import perf_counter
from pathlib import Path
from traceback import format_exc


UTC_OFFSET = datetime.now(timezone.utc).astimezone().utcoffset() // timedelta(hours=1)
CURRENT_TIMEZONE = timezone(timedelta(hours=UTC_OFFSET))
VALID_TIME_REGEX = re.compile(r'^[0-2][0-9]:[0-5][0-9]$')
VALID_DATE_REGEX = re.compile(r'^\d{4}-[0-1][0-9]-[0-3][0-9]$')


def run_cmd(cmd: str | list, cwd=None) -> tuple[str | None, str | None]:
    """
    Syncronously start a subprocess and run a command returning its output
    """
    if cwd is None:
        cwd = os.getcwd()

    proc = None
    if isinstance(cmd, str):
        proc = subprocess.Popen(cmd, cwd=cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
    elif isinstance(cmd, list):
        proc = subprocess.Popen(cmd, cwd=cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    stdout, stderr = proc.communicate()
    return (stdout.decode().strip() if stdout else None, stderr.decode().strip() if stderr else None, proc.returncode)


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


def get_page_by_rel(links: str, rel: str = 'last'):
    val = re.findall(rf'.*&page=(\d+).*>; rel="{rel}"', links)
    if val:
        return int(val[0])
    return None


def pformat_objects(x):
    try:
        copy = deepcopy(x)
        try:
            del copy['__builtins__']
        except Exception:
            pass
        if isinstance(copy, dict):
            for val in copy:
                if isinstance(copy[val], (str, int, bool, tuple, list, float, set, complex)):
                    continue
                copy[val] = getattr(copy[val], '__dict__', repr(copy[val]))
            return pformat(copy)
        elif isinstance(copy, (str, int, bool, tuple, list, float, set, complex)):
            return pformat(copy)
        else:
            return pformat(vars(copy))
    except Exception:
        try:
            copyd = dict(x)
            del copyd['__builtins__']
            return pformat(copyd)
        except Exception:
            pass
        return pformat(x)


def get_students(student_filename: str) -> dict:
    """
    Reads class roster csv in the format given by github classroom:
    "identifier","github_username","github_id","name"

    and returns a dictionary of students mapping github username to real name
    """
    students = {}  # student dict
    if Path(student_filename).exists():  # if classroom roster is found
        with open(student_filename, newline='') as f_handle:  # use with to auto close file
            csv_reader = csv.reader(f_handle)  # Use csv reader to separate values into a list
            next(csv_reader)  # skip header line
            for student in csv_reader:
                if not student or len(student) < 2:
                    continue
                name = re.sub(r'([.]\s?|[,]\s?|\s)', '-', student[0]).replace("'", '-').rstrip(r'-').strip()
                github = student[1].strip()
                if name and github:  # if csv contains student name and github username, map them to each other
                    students[github] = name
    else:
        raise Exception(f'Classroom roster `{student_filename}` does not exist.')
    return students  # return dict mapping names to github usernames


class LogLevel(Enum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class LogHandler:
    def __init__(self, log_level: LogLevel) -> None:
        self.log_level = log_level
        self.log_file_handler = None
        self.log_cache: dict[str, list] = {}
        self.log_level_strings = {LogLevel.DEBUG: 'DEBUG', LogLevel.INFO: 'INFO', LogLevel.WARNING: 'WARNING', LogLevel.ERROR: 'ERROR', LogLevel.CRITICAL: 'CRITICAL'}
        self.log_prefix = '%%DATETIME%% - [%%LOGLEVEL%%][%%CALLER%%]:'
        self.prefix_ljust = 25
        self.censored_strs = []

    def open(self, log_file: str) -> None:
        if self.log_file_handler is not None:
            return
        self.log_file_handler = open(log_file, 'w')

    def _fill_prefix(self, log_level: LogLevel, caller_str: str) -> str:
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return self.log_prefix.replace('%%DATETIME%%', current_datetime).replace('%%LOGLEVEL%%', self.log_level_strings[log_level]).replace('%%CALLER%%', caller_str).ljust(self.prefix_ljust)

    def _censor_str(self, log_str: str) -> str:
        for censored_str in self.censored_strs:
            log_str = log_str.replace(censored_str, '<REDACTED>')
        return log_str

    def _append(self, log_level: LogLevel, log_str: str, caller: str | object = 'MAIN') -> None:
        if log_level.value >= self.log_level.value:
            caller_str = caller if isinstance(caller, str) else caller.__class__.__name__.upper()
            if caller_str not in self.log_cache:
                self.log_cache[caller_str] = []
            self.log_cache[caller_str].append((log_level, self._censor_str(log_str)))

    def _flush(self) -> None:
        if self.log_file_handler is None:
            return
        for caller_str in self.log_cache:
            for log_level, log_str in self.log_cache[caller_str]:
                self._write(log_level, log_str, caller_str, flush=False)
            self.log_cache[caller_str].clear()

    def _write(self, log_level: LogLevel, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            return
        if flush:
            self._flush()
        caller_str = caller if isinstance(caller, str) else caller.__class__.__name__.upper()
        prefix = self._fill_prefix(log_level, caller_str)
        if log_level.value >= self.log_level.value:
            self.log_file_handler.write(f'{prefix}{self._censor_str(log_str)}\n')

    def debug(self, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(LogLevel.DEBUG, log_str, caller)
        else:
            self._write(LogLevel.DEBUG, log_str, caller, flush)

    def info(self, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(LogLevel.INFO, log_str, caller)
        else:
            self._write(LogLevel.INFO, log_str, caller, flush)

    def warning(self, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(LogLevel.WARNING, log_str, caller)
        else:
            self._write(LogLevel.WARNING, log_str, caller, flush)

    def error(self, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(LogLevel.ERROR, log_str, caller)
        else:
            self._write(LogLevel.ERROR, log_str, caller, flush)

    def critical(self, log_str: str, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(LogLevel.CRITICAL, log_str, caller)
        else:
            self._write(LogLevel.CRITICAL, log_str, caller, flush)

    def print_and_log(self, log_str: str, log_level: LogLevel, caller: str | object = 'MAIN', flush: bool = True) -> None:
        if self.log_file_handler is None:
            self._append(log_level, log_str, caller)
        else:
            self._write(log_level, log_str, caller, flush)
        print(log_str)

    def close(self) -> None:
        if self.log_file_handler is None:
            return
        self._flush()
        self.log_file_handler.close()
        self.log_file_handler = None


STATUS_LJUST = 40


class RepoStatus(Enum):
    """
    Enum for repo status
    tuple values = (int value, friendly print string, color, status means done)
    """

    # errors (only LIGHT_RED)
    RESET_ERROR      = (-5, 'Reset Error'.ljust(STATUS_LJUST),    LIGHT_RED,  True)
    CLONE_ERROR      = (-4, 'Clone Error'.ljust(STATUS_LJUST),    LIGHT_RED,  True)
    ACTIVITY_ERROR   = (-3, 'Activity Error'.ljust(STATUS_LJUST), LIGHT_RED,  True)
    RETRIEVE_ERROR   = (-2, 'Retrieve Error'.ljust(STATUS_LJUST), LIGHT_RED,  True)
    ERROR            = (-1, 'Unknown Error'.ljust(STATUS_LJUST),  LIGHT_RED,  True)

    # neutral/in-progress (WHITE)
    INIT             = ( 0, 'Initial State'.ljust(STATUS_LJUST),       WHITE, False)
    RETRIEVING       = ( 1, 'Retrieving...'.ljust(STATUS_LJUST),       WHITE, False)
    CHECKING_COMMITS = ( 4, 'Checking Commits...'.ljust(STATUS_LJUST), WHITE, False)
    CLONING          = ( 8, 'Cloning...'.ljust(STATUS_LJUST),          WHITE, False)
    CLONED           = ( 9, 'Cloning...'.ljust(STATUS_LJUST),          WHITE, False)
    RESETTING        = (10, 'Resetting...'.ljust(STATUS_LJUST),        WHITE, False)

    # success (GREEN)
    RETRIEVED        = ( 2, 'Repo Found.'.ljust(STATUS_LJUST), LIGHT_GREEN,   False)
    COMMIT_FOUND     = ( 5, 'Commit Found.'.ljust(STATUS_LJUST), LIGHT_GREEN, False)
    CLONED_DONE      = ( 9, 'Cloned'.ljust(STATUS_LJUST), LIGHT_GREEN,         True)
    RESET            = (11, 'Reset'.ljust(STATUS_LJUST), LIGHT_GREEN,          True)

    # warnings, each with its own hue
    NOT_FOUND        = ( 3, 'Repo Does Not Exist.'.ljust(STATUS_LJUST),  YELLOW,                  True)
    NO_COMMITS       = ( 6, 'Repo Has No Commits.'.ljust(STATUS_LJUST),    CYAN,                  True)
    COMMIT_NOT_FOUND = ( 7, 'Commit Not Found Before Due Datetime.'.ljust(STATUS_LJUST), MAGENTA, True)


class APIClient:
    def __init__(self, access_token: str, organization: str, headers: dict, log_handler: LogHandler) -> None:
        self.access_token = access_token
        self.organization = organization
        self.headers = headers
        self.log_handler = log_handler
        self.debug = self.log_handler.log_level == LogLevel.DEBUG
        self.session = None

        #self.prefix_exists_params
        #self.push_params

    def sync_request(self, url: str, params: dict = None):
        import niquests

        if self.session is None:
            self.session = niquests.Session(pool_maxsize=1000, multiplexed=True, disable_http1=True)
            if self.debug:
                self.log_handler.info('Session Created.', self)
                self.log_handler.debug('*** SESSION ***', self)
                self.log_handler.debug(pformat_objects(self.session), self)
                self.log_handler.debug('*' * 50, self)
        if params is None:
            params = {}

        url = f'{url}?{urlencode(params)}'
        response = self.session.get(url, headers=self.headers)
        if self.debug:
            self.log_handler.debug(f'*** API RESPONSE [URL={url}] ***', self)
            self.log_handler.debug(pformat_objects(response), self)
            self.log_handler.debug('*' * 50, self)
        return response

    def repo_prefix_exists(self, repo_prefix: str):
        raise NotImplementedError()

    def get_commit_before_by_repo(self, datetime: datetime, repo):
        raise NotImplementedError()

    def get_repo(self, repo: 'GitRepo') -> dict:
        raise NotImplementedError()

    def get_push_count(self, repo: 'GitRepo') -> dict:
        raise NotImplementedError()

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None
        if self.log_handler is not None:
            self.log_handler.close()
            self.log_handler = None


class GitRepo:
    def __init__(self, api_client: APIClient, repo_info: dict = None, status: RepoStatus = RepoStatus.INIT, prefix: str = None, real_name: str = None, username: str = None, local_path: str = None, hours_adjust: int = 0) -> None:
        self.repo_info = repo_info
        self.prefix = prefix
        self.real_name = real_name
        self.username = username
        self.local_path = local_path
        self.status = status
        self.out_name = f'{self.prefix}-{self.real_name}'
        self.status = RepoStatus.INIT
        self.api_client = api_client
        self.hours_adjust = timedelta(hours=hours_adjust)

    def __repr__(self):
        return f'<GitRepo: {self.prefix}-{self.username}, status={self.status}, hours_adjust={self.hours_adjust}, repo_info={self.repo_info}>'

    def get_info(self):
        self.status = RepoStatus.RETRIEVING
        response_status_code, self.repo_info = self.api_client.get_repo(self)
        if response_status_code == 200:
            self.status = RepoStatus.RETRIEVED
        elif response_status_code == 404:
            self.status = RepoStatus.NOT_FOUND
        else:
            self.status = RepoStatus.RETRIEVE_ERROR
        return self

    def get_commit_before(self, datetime: datetime):
        return self.api_client.get_commit_before_by_repo(datetime + self.hours_adjust, self)

    def clone(self, out_dir: Path | str, depth: int = None, single_branch: bool = True, use_cloned_done: bool = False, dry_run: bool = False):
        self.status = RepoStatus.CLONING
        clone_url = self.get_clone_url()
        if clone_url is None:
            self.status = RepoStatus.CLONE_ERROR
            return None, None, -1
        cmd = ['git', 'clone']
        if single_branch:
            cmd.append('--single-branch')
        if depth is not None:
            cmd.extend(['--depth', str(depth)])
        cmd.extend([clone_url, self.out_name])
        self.local_path = Path(out_dir) / self.out_name
        stdout, stderr, exitcode = None, None, 0
        if not dry_run:
            stdout, stderr, exitcode = run_cmd(cmd, cwd=out_dir)
        if exitcode == 0:
            self.status = RepoStatus.CLONED if not use_cloned_done else RepoStatus.CLONED_DONE
        else:
            self.status = RepoStatus.CLONE_ERROR
        return stdout, stderr, exitcode

    def reset(self, commit_hash: str, dry_run: bool = False):
        self.status = RepoStatus.RESETTING
        cmd = ['git', 'reset', '--hard', '-q', commit_hash]
        stdout, stderr, exitcode = None, None, 0
        if not dry_run:
            stdout, stderr, exitcode = run_cmd(cmd, cwd=self.local_path)
        if exitcode == 0:
            self.status = RepoStatus.RESET
        else:
            self.status = RepoStatus.RESET_ERROR
        return stdout, stderr, exitcode

    def clone_and_reset(self, commit_hash, out_dir: Path | str, depth: int = None, single_branch: bool = True, dry_run: bool = False):
        clone_stdout, clone_stderr, clone_exitcode = self.clone(out_dir, depth, single_branch, dry_run=dry_run)
        if clone_exitcode != 0:
            return (clone_stdout, clone_stderr, clone_exitcode), (None, None, None)
        reset_stdout, reset_stderr, reset_exitcode = self.reset(commit_hash, dry_run=dry_run)
        return (clone_stdout, clone_stderr, clone_exitcode), (reset_stdout, reset_stderr, reset_exitcode)

    def get_name(self):
        raise NotImplementedError()

    def get_clone_url(self):
        raise NotImplementedError()


class GitHubRepo(GitRepo):
    def get_name(self):
        return f'{self.prefix}-{self.username}'

    def get_clone_url(self):
        return self.repo_info.get('clone_url', None).replace('https://', f'https://{self.api_client.access_token}@')


class GitLabRepo(GitRepo):
    def get_name(self):
        return f'{self.real_name.replace("-", "_")}/{self.prefix}'

    def get_clone_url(self):
        return self.repo_info.get('ssh_url_to_repo', None)


class GitHubAPIClient(APIClient):
    def __init__(self, config, log_handler: LogHandler) -> None:
        access_token = config.github_token
        organization = config.github_organization
        headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {access_token}',
            'X-GitHub-Api-Version': '2022-11-28',
        }
        if not access_token:
            del headers['Authorization']

        self.repo_params = {'q': f'org:{organization} fork:true', 'per_page': 100}

        self.push_params = {'activity_type': 'push,force_push', 'order': 'desc', 'per_page': 100, 'page': 1}
        self.commit_params = {'per_page': 1, 'page': 1}
        super().__init__(access_token, organization, headers, log_handler)

    def repo_prefix_exists(self, repo_prefix: str) -> tuple:
        """
        Check if assignment exists
        """
        import orjson as jsonbackend

        if not repo_prefix:
            return True, -1
        params = dict(self.repo_params)
        params['per_page'] = 1
        params['q'] = f'{repo_prefix} ' + params['q']
        url = 'https://api.github.com/search/repositories'
        response = self.sync_request(url, params)
        if response.status_code != 200:
            return 0
        repo_json = jsonbackend.loads(response.content)
        if repo_json.get('total_count', 0) == 0:
            return 0
        return repo_json['total_count']

    def get_page_by_number(self, base_url: str, params: dict, page: int):
        params = dict(params)
        params['page'] = page
        return self.sync_request(base_url, params)

    def fetch_all_pages(self, base_url: str, params: dict):
        import orjson as jsonbackend

        # Get first page
        response = self.get_page_by_number(base_url, params, 1)
        data = jsonbackend.loads(response.content)
        items = None
        if isinstance(data, dict):
            items = data.get('items', [])
        elif isinstance(data, list):
            items = data
        if not items:
            yield data
            return  # required to exit generator

        last_page = get_page_by_rel(response.headers.get('link', ''), 'last')
        if not last_page:
            yield items
            return  # required to exit generator
        yield items

        # Get remaining pages
        with ThreadPoolExecutor(max_workers=(os.cpu_count() * 1.25) if not self.debug else 1) as executor:
            futures = [executor.submit(self.get_page_by_number, base_url, params, page) for page in range(2, last_page + 1)]
            for future in as_completed(futures):
                response = future.result()
                data = jsonbackend.loads(response.content)
                items = None
                if isinstance(data, dict):
                    items = data.get('items', [])
                elif isinstance(data, list):
                    items = data
                yield items

    def get_commit_before_by_pushes(self, datetime: datetime, pushes: dict) -> str:
        for push in pushes:
            push_time = datetime.strptime(push['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
            if push_time < datetime:
                return push['after']
        return None

    def get_push_count(self, repo: 'GitHubRepo') -> int:
        if repo.status != RepoStatus.RETRIEVED:
            return None
        repo.status = RepoStatus.CHECKING_COMMITS

        import orjson as jsonbackend

        params = dict(self.push_params)
        url = f'{repo.repo_info["url"]}/activity'
        response = self.sync_request(url, params)
        if response.status_code != 200:
            repo.status = RepoStatus.ACTIVITY_ERROR
            return -1
        pushes = jsonbackend.loads(response.content)
        num_pushes = len(pushes)
        if num_pushes == 0:
            repo.status = RepoStatus.NO_COMMITS
        return num_pushes

    def get_commit_before_by_repo(self, datetime: datetime, repo: 'GitHubRepo') -> tuple[str, int]:
        # TODO: Support github classroom team repos, owned by the org, check "teams_url", and then "members_url" in repo json to get students in team
        try:
            if repo.status != RepoStatus.RETRIEVED:
                return None
            repo.status = RepoStatus.CHECKING_COMMITS
            params = dict(self.push_params)
            # params['actor'] = repo['student_github']

            # datetime = self.get_adjusted_due_datetime(repo, due_date, due_time)  # adjust based on student parameters, Timezone, and DST
            # GitHub API {owner}/{repo}/activity endpoint allows to query all pushes for a repo by a user
            url = f'{repo.repo_info["url"]}/activity'
            num_pushes = 0
            for pushes in self.fetch_all_pages(url, params):
                num_pushes += len(pushes)
                commit_hash = self.get_commit_before_by_pushes(datetime, pushes)
                if commit_hash is not None:
                    repo.status = RepoStatus.COMMIT_FOUND
                    return commit_hash
            if num_pushes == 0:
                repo.status = RepoStatus.NO_COMMITS
            else:
                repo.status = RepoStatus.COMMIT_NOT_FOUND
            return None
        except Exception as _:
            repo.status = RepoStatus.ACTIVITY_ERROR

    def get_repo(self, repo: GitRepo) -> dict:
        import orjson as jsonbackend

        response = self.sync_request(f'https://api.github.com/repos/{self.organization}/{repo.prefix}-{repo.username}')
        return response.status_code, jsonbackend.loads(response.content)

    def search_repos(self, repo_prefix: str):
        """
        Return all repos that have at least one commit before due date/time
        and are from students in class roster and are only for the desired assignment
        """
        params = dict(self.repo_params)

        if repo_prefix:
            params['q'] = f'{repo_prefix} ' + params['q']

        url = 'https://api.github.com/search/repositories'
        for repo_infos in self.fetch_all_pages(url, params):
            for repo_info in repo_infos:
                yield repo_info

    def get_repo_of_users(self, repo_prefix: str, usernames: list | dict):
        import orjson as jsonbackend

        base_url = f'https://api.github.com/repos/{self.organization}/'
        with ThreadPoolExecutor(max_workers=(os.cpu_count() * 1.25) if not self.debug else 1) as executor:
            futures = {executor.submit(self.sync_request, f'{base_url}{repo_prefix}-{username}', {}): username for username in usernames}
            for future in as_completed(futures):
                response = future.result()
                yield response.status_code, jsonbackend.loads(response.content)


class GitLabAPIClient(APIClient):
    def __init__(self, config, log_handler: LogHandler) -> None:
        access_token = config.gitlab_token
        organization = config.gitlab_organization
        self.server_url = config.gitlab_server
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        if not access_token:
            del headers['Authorization']

        self.prefix_exists_params = {'scope': 'projects'}
        self.push_params = {'action': 'pushed', 'per_page': 1}

        super().__init__(access_token, organization, headers, log_handler)

    def repo_prefix_exists(self, repo_prefix: str):
        """
        Check if assignment exists
        """
        import orjson as jsonbackend

        if not repo_prefix:
            return True, -1
        params = dict(self.prefix_exists_params)
        params['search'] = f'starter_code/{repo_prefix}'
        url = f'{self.server_url}/api/v4/groups/{quote(self.organization)}/search'
        response = self.sync_request(url, params)
        if response.status_code != 200:
            return 0
        repo_json = jsonbackend.loads(response.content)
        return len(repo_json)

    def get_push_count(self, repo: 'GitLabRepo'):
        try:
            if repo.status != RepoStatus.RETRIEVED:
                return None
            repo.status = RepoStatus.CHECKING_COMMITS
            params = dict(self.push_params)

            import orjson as jsonbackend

            repo_id = repo.repo_info.get('id', None)
            url = f'{self.server_url}/api/v4/projects/{repo_id}/events'
            response = self.sync_request(url, params)
            if response.status_code != 200:
                repo.status = RepoStatus.ACTIVITY_ERROR
                return -1
            num_pushes = len(jsonbackend.loads(response.content))
            if num_pushes == 0:
                repo.status = RepoStatus.NO_COMMITS
            return num_pushes
        except Exception as _:
            repo.status = RepoStatus.ACTIVITY_ERROR

    def get_commit_before_by_repo(self, datetime: datetime, repo: 'GitLabRepo'):
        try:
            if repo.status != RepoStatus.RETRIEVED:
                return None
            repo.status = RepoStatus.CHECKING_COMMITS
            params = dict(self.push_params)

            repo_id = repo.repo_info.get('id', None)
            url = f'{self.server_url}/api/v4/projects/{repo_id}/events'
            response = self.sync_request(url, params)
            if response.status_code != 200:
                repo.status = RepoStatus.ACTIVITY_ERROR
                return -1
            has_pushes = len(response.json()) > 0
            if not has_pushes:
                repo.status = RepoStatus.NO_COMMITS
                return None

            params['before'] = datetime.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            response = self.sync_request(url, params)
            if response.status_code != 200:
                repo.status = RepoStatus.ACTIVITY_ERROR
                return -1

            pushes = response.json()
            if not pushes:
                repo.status = RepoStatus.COMMIT_NOT_FOUND
                return None

            commit_hash = pushes[0]['push_data']['commit_to']
            repo.status = RepoStatus.COMMIT_FOUND
            return commit_hash
        except Exception as _:
            repo.status = RepoStatus.ACTIVITY_ERROR

    def get_repo(self, repo: GitRepo) -> dict:
        import orjson as jsonbackend
        # repo.prefix
        student_group_name = repo.real_name.replace("-", "_")
        search_term = repo.prefix
        search_group = f'{self.organization}/students/{student_group_name}'

        response = self.sync_request(f'{self.server_url}/api/v4/groups/{quote(search_group, safe="")}/search', {'scope': 'projects', 'search': search_term})
        data = jsonbackend.loads(response.content)
        if isinstance(data, list) and len(data) > 0:
            return response.status_code, data[0]
        if not isinstance(data, list):
            self.log_handler.error(f'Unexpected data returned from GitLab API when searching for repo `{search_term}` in group `{search_group}`: {pformat_objects(data)}', self)
            return response.status_code, data
        return 404, data


def repo_status_print_loop(repos: list[GitHubRepo], max_name_len: int, max_user_len: int):
    i = 0
    # Continue to print until all repos have a status that means they have no more work to do
    while not all(repo.status.value[3] for repo in repos):
        if i == 0:
            i += 1
            for _, repo in enumerate(repos):
                base_str = build_repo_and_info_str(repo, repo.status.value[1], max_name_len, max_user_len, color=repo.status.value[2])
                print(f'  > {base_str}')
        vals = range(len(repos), -1, -1)
        for i, repo in enumerate(repos):
            base_str = build_repo_and_info_str(repo, repo.status.value[1], max_name_len, max_user_len, color=repo.status.value[2])
            print_positional_line(f'  > {base_str}', vals[i])
    for i, repo in enumerate(repos):
        base_str = build_repo_and_info_str(repo, repo.status.value[1], max_name_len, max_user_len, color=repo.status.value[2])
        print_positional_line(f'  > {base_str}', vals[i])


def get_utc_w_daylight_savings_adjustment(due_date: str, due_time: str) -> datetime:
    due_datetime = datetime.strptime(f'{due_date} {due_time}', '%Y-%m-%d %H:%M') - timedelta(hours=UTC_OFFSET)  # convert to UTC
    time_diff = due_datetime.hour - due_datetime.astimezone(CURRENT_TIMEZONE).hour  # check if current time's Daylight Savings Time is different from due date/time
    is_dst_diff = time_diff != 0
    if is_dst_diff:
        due_datetime -= timedelta(hours=time_diff)
    # want to get pushes that happened before due date/time, so add a minute to due date/time
    due_datetime = due_datetime + timedelta(minutes=1)
    return due_datetime


def make_unique_path(path: Path) -> Path:
    if not path.exists():
        os.makedirs(path)
        return path
    path_str = str(path)
    i = 1
    while path.exists():
        path = Path(f'{path_str}_{i}')
        i += 1
    os.makedirs(path)
    return path


def onerror(func, path: str, exc_info) -> None:
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def delete_files_in_dir(path: Path, dry_run: bool = False):
    if Path(path).exists():
        if dry_run:
            num_files = len(os.listdir(path))
            return num_files
        else:
            num_files = len(os.listdir(path))
            for folder in os.listdir(path):
                if (Path(path) / folder).is_dir():
                    shutil.rmtree(Path(path) / folder, onexc=onerror)
                else:
                    os.remove(Path(path) / folder)
            return num_files


def get_repo_prefix(client: GitHubAPIClient, prev_repo_prefix: str) -> str:
    """
    Get assignment name from input.
    If input is empty, prompt to use previous value.

    TODO: CLEAN!!!!!
    """
    if prev_repo_prefix:
        repo_prefix = input('Repo Prefix (`enter` for previous value): ')  # get assignment name (repo prefix)
        repo_prefix = repo_prefix if repo_prefix else prev_repo_prefix if bool_prompt(f'Use previous repo prefix: `{prev_repo_prefix}`?', True) else repo_prefix
        prev_repo_prefix = repo_prefix
        repo_count = client.repo_prefix_exists(repo_prefix)
        while not repo_prefix or not repo_count:  # if input is empty ask again
            if repo_prefix == 'quit()':
                return repo_prefix
            if not repo_count:
                print(f'Repo prefix `{repo_prefix}` not found. Please try again.')
            repo_prefix = input('Please input a repo prefix: ')
            repo_prefix = repo_prefix if repo_prefix else prev_repo_prefix if bool_prompt(f'Use previous repo prefix: `{prev_repo_prefix}`?', True) else repo_prefix
            repo_count = client.repo_prefix_exists(repo_prefix)
        return repo_prefix
    else:
        repo_prefix = input('Repo Prefix: ')  # get assignment name (repo prefix)
        while not repo_prefix:
            repo_prefix = input('Please input a repo prefix: ')
        prev_repo_prefix = repo_prefix
        repo_count = client.repo_prefix_exists(repo_prefix)
        while not repo_prefix or not repo_count:  # if input is empty ask again
            if repo_prefix == 'quit()':
                return repo_prefix
            if not repo_count:
                print(f'Repo prefix `{repo_prefix}` not found. Please try again.')
            repo_prefix = input('Please input a repo prefix: ')
            repo_prefix = repo_prefix if repo_prefix else prev_repo_prefix if bool_prompt(f'Use previous repo prefix: `{prev_repo_prefix}`?', True) else repo_prefix
            repo_count = client.repo_prefix_exists(repo_prefix)
        return repo_prefix


def create_vscode_workspace(parent_folder_path, repo_prefix, repos: list[GitHubRepo]):
    workspace_path = Path(parent_folder_path) / f'{repo_prefix}.code-workspace'
    with open(workspace_path, 'w') as f:
        f.write('{\n')
        f.write('    "folders": [\n')
        for repo in sorted(repos, key=lambda x: x.out_name):
            if repo.status != RepoStatus.CLONED_DONE and repo.status != RepoStatus.RESET:
                continue
            val = repo.out_name
            f.write(f'        {{ "path": "{val}" }},\n')
        f.write('    ],\n\t"settings": {}\n')
        f.write('}\n')
    print(f'{LIGHT_GREEN}VSCode workspace file created at {workspace_path}.{WHITE}')


def extract_data_folder(initial_path, data_folder_name='data'):
    repos = os.listdir(initial_path)
    repo_to_check = repos[len(repos) - 1]
    folders = os.listdir(Path(initial_path) / repo_to_check)
    if data_folder_name in folders:
        shutil.copytree(f'{str(Path(initial_path) / repo_to_check / data_folder_name)}', f'{str(Path(initial_path) / data_folder_name)}')
        print(
            f'{LIGHT_GREEN}Data folder extracted to the output directory.{WHITE}',
        )


def print_pull_report(students, num_repos, num_not_accepted, num_no_commits, num_cloned, num_reset, exec_time: float, dry_run: bool, current_pull: bool) -> str:
    """
    Give end-user somewhat detailed report of what repos were able to be cloned, how many students accepted the assignments, etc.
    """
    done_str = f'{LIGHT_GREEN}Done in {round(exec_time, 2)} seconds.{WHITE}'
    total_assignment_repos = num_repos

    num_accepted = len(students) - num_not_accepted
    section_students = len(students)
    accept_str = f'{LIGHT_GREEN}{num_accepted}{WHITE}' if num_accepted == section_students else f'{LIGHT_RED}{num_accepted}{WHITE}'
    full_accept_str = f'{accept_str}{LIGHT_GREEN}/{len(students)} accepted the assignment before due datetime.{WHITE}'

    commits_str = f'{LIGHT_GREEN}{num_no_commits}{WHITE}' if num_no_commits == 0 else f'{LIGHT_RED}{num_no_commits}{WHITE}'
    full_commits_str = f'{commits_str}{LIGHT_GREEN}/{num_accepted} had no commits.'

    clone_str = f'{LIGHT_GREEN}{num_cloned}{WHITE}' if num_cloned == total_assignment_repos else f'{LIGHT_RED}{num_cloned}{WHITE}'
    full_clone_str = f'{LIGHT_GREEN}Cloned {clone_str}{LIGHT_GREEN}/{total_assignment_repos} repos.{WHITE}'

    rolled_back_str = f'{LIGHT_GREEN}{num_reset}{WHITE}' if num_reset == num_cloned else f'{LIGHT_RED}{num_reset}{WHITE}'
    full_rolled_back_str = f'{LIGHT_GREEN}Rolled back {rolled_back_str}{LIGHT_GREEN}/{num_reset} repos.{WHITE}'

    print()
    print(done_str)
    print(full_accept_str)
    if not current_pull:
        print(full_commits_str)
    print(full_clone_str)
    if not current_pull:
        print(full_rolled_back_str)
    print()

    full_report_str = f'\n{done_str}\n{full_accept_str}\n{full_commits_str}\n{full_clone_str}\n{full_rolled_back_str}'
    return full_report_str


def get_time():
    """
    Get assignment due time from input.
    """
    valid_time_regex = VALID_TIME_REGEX
    current = False
    prompt = 'Time Due (24hr HH:MM, press `enter` for current): '
    time_due = input(prompt)  # get time assignment was due
    if not time_due:  # if time due is blank use current time
        current = True
        current_time = datetime.now()  # get current time
        time_due = current_time.strftime('%H:%M')  # format current time into hour:minute 24hr format
        print(f'Using current time: {time_due}')  # output what is being used to end user
    else:
        while not valid_time_regex.match(time_due):
            print(f'{LIGHT_RED}Invalid time format. Please use 24hr HH:MM format.{WHITE}')
            time_due = input(prompt)
    return current, time_due


def get_date():
    """
    Get assignment due date from input.
    """
    valid_date_regex = VALID_DATE_REGEX
    current = False
    prompt = 'Date Due (format = yyyy-mm-dd, press `enter` for current): '
    date_due = input(prompt)  # get due date
    if not date_due:  # If due date is blank use current date
        current = True
        current_date = date.today()  # get current date
        date_due = current_date.strftime('%Y-%m-%d')  # get current date in year-month-day format
        print(f'Using current date: {date_due}')  # output what is being used to end user
    else:
        while not valid_date_regex.match(date_due):
            print(f'{LIGHT_RED}Invalid date format. Please use yyyy-mm-dd format.{WHITE}')
            date_due = input(prompt)
    return current, date_due


def print_positional_line(text: str, y: int):
    """
    build text at a specific position y on the terminal
    y = 0 is the bottom of the terminal
    """
    start_of_prev_line = '\033[F'
    start_of_next_line = '\033[E'
    print(f'{start_of_prev_line * y}{text}{start_of_next_line * y}', end='')


def build_repo_and_info_str(repo: GitRepo, info: str, max_name_len: int, max_user_len: int, color: str = WHITE) -> str:
    return f'{color}{repo.real_name.ljust(max_name_len)} : {repo.username.ljust(max_user_len)} : {info}{WHITE}'


def get_repos_info(repos: list[GitRepo], debug: bool = False):
    with ThreadPoolExecutor(max_workers=(os.cpu_count() * 1.25) if not debug else 1) as executor:
        futures = [executor.submit(repo.get_info) for repo in repos]
        for future in as_completed(futures):
            yield future.result()


def print_and_log(message, prints_log):
    prints_log.append(message)
    print(message)


def save_report(report, config_manager):
    clone_logs = config_manager.config.clone_history
    clone_logs.append(report)
    if len(clone_logs) > 8:
        clone_logs = clone_logs[1:]
    config_manager.set_config_value('clone_history', clone_logs)


def main(preset=None, dry_run=None, config_manager=None):
    gc.disable()
    log_handler = None
    client = None

    start_1 = perf_counter()
    prints_log = []
    repos_created = False
    debug = config_manager.config.debug
    students_path = config_manager.config.students_csv
    default_clone_source = config_manager.config.default_clone_source
    stop_1 = perf_counter()
    try:
        if preset is None:
            preset = ClonePreset('', '', '', students_path, False, (0, 0, 0), default_clone_source)
            preset.append_timestamp = bool_prompt(
                'Append timestamp to repo folder name?',
                not config_manager.config.replace_clone_duplicates,
            )
            github_src_str = f'{LIGHT_GREEN}GitHub{WHITE}' if default_clone_source == 'GitHub' else 'GitHub'
            gitlab_src_str = f'{LIGHT_GREEN}GitLab{WHITE}' if default_clone_source == 'GitLab' else 'GitLab'
            preset.clone_source = multichoice_prompt(
                'Choose a clone source (enter for default):',
                [github_src_str, gitlab_src_str],
                0 if default_clone_source == 'GitHub' else 1,
            )
            preset.clone_source = 'GitHub' if preset.clone_source == github_src_str else 'GitLab'
        else:
            students_path = preset.csv_path
        start_2 = perf_counter()
        students = get_students(students_path)
        append_timestamp = preset.append_timestamp
        folder_suffix = preset.folder_suffix

        clone_source = preset.clone_source if preset.clone_source else default_clone_source
        if clone_source not in ['GitHub', 'GitLab']:
            print(f'{LIGHT_RED}Invalid clone source. Please choose either GitHub or GitLab.{WHITE}')
            return

        if clone_source == 'GitHub' and (not config_manager.config.github_token or not config_manager.config.github_organization):
            print(f'{LIGHT_RED}GitHub token or organization not set in config. Please set them and try again.{WHITE}')
            return

        if clone_source == 'GitLab' and (not config_manager.config.gitlab_token or not config_manager.config.gitlab_organization or not config_manager.config.gitlab_server):
            print(f'{LIGHT_RED}GitLab token, organization, or server not set in config. Please set them and try again.{WHITE}')
            return

        client_type = GitHubAPIClient if clone_source == "GitHub" else GitLabAPIClient
        repo_type = GitHubRepo if clone_source == "GitHub" else GitLabRepo
        access_token = config_manager.config.github_token if clone_source == "GitHub" else config_manager.config.gitlab_token
        organization = config_manager.config.github_organization if clone_source == "GitHub" else config_manager.config.gitlab_organization
        delete_duplicates = config_manager.config.replace_clone_duplicates


        log_handler = LogHandler(LogLevel.DEBUG if debug else LogLevel.CRITICAL)
        log_handler.censored_strs.append(access_token)
        client = client_type(config_manager.config, log_handler)
        stop_2 = perf_counter()

        prev_repo_prefix = '' if not config_manager.config.clone_history else config_manager.config.clone_history[-1].assignment_name
        repo_prefix = get_repo_prefix(client, prev_repo_prefix)
        if repo_prefix == 'quit()':
            return

        flags = preset.clone_type  # (class activity, assignment, exam)
        students_adjust = {}
        for param in config_manager.config.extra_student_parameters:
            param: StudentParam
            if param.github not in students:
                continue
            if flags is None:
                print(f'{LIGHT_GREEN}Student found in extra parameters.{WHITE}')
                res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ').lower()
                while res != 'ca' and res != 'as' and res != 'ex':
                    res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ').lower()
                    # is_ca = flags[0]
                    # is_as = flags[1]
                    # is_ex = flags[2]
                if res == 'ca':
                    flags = (1, 0, 0)
                elif res == 'as':
                    flags = (0, 1, 0)
                elif res == 'ex':
                    flags = (0, 0, 1)
            hours_adjust = 0
            if flags[0]:
                hours_adjust = param.class_activity_hours
            elif flags[1]:
                hours_adjust = param.assignment_hours
            elif flags[2]:
                hours_adjust = param.exam_hours
            students_adjust[param.github] = hours_adjust

        current_pull = False
        if debug:
            log_handler.info('*** Starting Parameters ***')
            log_handler.info(f'Access Token: {access_token}')
            log_handler.info(f'Students CSV: {students_path}')
            log_handler.info(f'Organization: {organization}')
            log_handler.info(f'Dry Run: {dry_run}')
            log_handler.info(f'Current Pull: {current_pull}')
            log_handler.info(f'Delete Duplicates: {delete_duplicates}')
            log_handler.info(f'Append Timestamp: {append_timestamp}')
            log_handler.info(f'Folder Suffix: {folder_suffix}')
            log_handler.info(f'Students: {students}')

        max_name_len = max([len(students[student]) for student in students])
        max_user_len = max([len(student) for student in students])

        due_date = ''
        due_time = ''
        time_is_current = False
        if not preset.clone_time:
            time_is_current, due_time = get_time()
        else:
            due_time = preset.clone_time

        date_is_current, due_date = get_date()

        if date_is_current and time_is_current:
            current_pull = True

        if append_timestamp:
            date_str = due_date[4:].replace('-', '_')
            time_str = preset.clone_time.replace(':', '_')
            folder_suffix += f'_{date_str}_{time_str}'

        due_datetime = get_utc_w_daylight_savings_adjustment(due_date, due_time)
        if date_is_current and time_is_current:
            current_pull = True

        if debug:
            log_handler.info(f'Assignment Name: {repo_prefix}')
            log_handler.info(f'Due Date: {due_date}')
            log_handler.info(f'Due Time: {due_time}')
            log_handler.info(f'Adjusted Due Datetime: {due_datetime} UTC')

        if append_timestamp:
            date_str = due_date[4:].replace('-', '_')
            time_str = due_time.replace(':', '_')
            folder_suffix += f'_{date_str}_{time_str}'

        start_3 = perf_counter()
        out_dir = Path(f'{config_manager.config.out_dir}/{repo_prefix}{folder_suffix}')
        if out_dir.exists() and not delete_duplicates:
            out_dir = make_unique_path(out_dir)
        elif out_dir.exists() and delete_duplicates:
            if debug:
                log_handler.info(f'Deleting files in {out_dir}')
            num_files_deleted = delete_files_in_dir(out_dir, dry_run)
            if dry_run:
                print_and_log(f'{CYAN}[INFO]: Would have deleted {num_files_deleted} files/folders in {out_dir}.{WHITE}', prints_log)
            else:
                print_and_log(f'{CYAN}[INFO]: Deleted {num_files_deleted} files/folders in {out_dir}.{WHITE}', prints_log)
        elif not dry_run:
            os.makedirs(out_dir)

        if debug:
            log_handler.info(f'Output directory: {out_dir}')
            log_handler.open(f'{out_dir}/log.txt')
            log_handler._flush()

        outdir_str = f'Output directory: {out_dir}'
        print_and_log(f'{outdir_str}', prints_log)
        stop_3 = perf_counter()

        num_repos = 0
        num_not_accepted = 0
        num_no_commit = 0
        num_cloned = 0
        num_reset = 0
        skip_flag = True
        pull_start = perf_counter()
        repos = [repo_type(client, prefix=repo_prefix, username=student_username, real_name=students[student_username]) for student_username in students]
        repos_created = True
        for repo in repos:
            if repo.username in students_adjust:
                repo.hours_adjust = students_adjust[repo.username]
        p_thread = None
        if not debug:
            from threading import Thread

            p_thread = Thread(target=repo_status_print_loop, args=(repos, max_name_len, max_user_len), daemon=True)
            p_thread.start()
        with ThreadPoolExecutor(max_workers=int((os.cpu_count() * 1.5) if not debug else 1)) as executor:
            get_futures = {}
            if current_pull:
                get_futures = {executor.submit(client.get_push_count, repo): repo for repo in get_repos_info(repos)}
            else:
                get_futures = {executor.submit(client.get_commit_before_by_repo, due_datetime, repo): repo for repo in get_repos_info(repos)}
            clone_futures = {}
            for future in as_completed(get_futures):
                due_commit = future.result()
                repo: GitHubRepo = get_futures[future]
                if debug:
                    log_handler.info(f'Get Future Done: {due_commit}, repo={pformat_objects(repo)}')
                if repo.status == RepoStatus.NOT_FOUND:
                    num_not_accepted += 1
                    continue
                num_repos += 1
                if repo.status == RepoStatus.NO_COMMITS:
                    num_no_commit += 1
                    # check_dups_futures[executor.submit(repo.find_duplicates)] = repo
                    continue
                if repo.status == RepoStatus.COMMIT_NOT_FOUND:
                    num_not_accepted += 1
                    continue
                if not current_pull:
                    skip_flag = False
                    clone_futures[executor.submit(repo.clone_and_reset, due_commit, out_dir, dry_run=dry_run)] = repo
                else:
                    skip_flag = False
                    clone_futures[executor.submit(repo.clone, out_dir, depth=1, use_cloned_done=True, dry_run=dry_run)] = repo

            for future in as_completed(clone_futures):
                clone_result, reset_result = None, None
                if not dry_run and not current_pull:
                    clone_result, reset_result = future.result()
                elif not dry_run and current_pull:
                    clone_result = future.result()
                repo: GitHubRepo = clone_futures[future]
                if debug:
                    log_handler.info(f'Clone Future Done: {clone_result}, {reset_result}, repo={pformat_objects(repo)}')
                if clone_result is not None and clone_result[2] == 0:
                    num_cloned += 1
                if reset_result is not None and reset_result[2] == 0:
                    num_reset += 1

        if not debug:
            p_thread.join()
            log_handler.info('Repo status print thread done.')
        pull_stop = perf_counter()
        ellapsed_time = (pull_stop - pull_start) + (stop_1 - start_1) + (stop_2 - start_2) + (stop_3 - start_3)

        clear()
        print('Clone Source:'.ljust(23), f'`{clone_source}`')
        print('Repo Prefix:'.ljust(23), f'`{repo_prefix}`')
        print('Due Date:'.ljust(23), f'`{due_date}`')
        print('Due Time:'.ljust(23), f'`{due_time}`')
        print('Adj. Date/Time (UTC):'.ljust(23), f'`{due_datetime} UTC`')
        print('Adj. Date/Time (Local):'.ljust(23), f'`{due_datetime + timedelta(hours=UTC_OFFSET)} {CURRENT_TIMEZONE}`')
        print('Current Pull:'.ljust(23), f'`{current_pull}`')
        print('Dry Run:'.ljust(23), f'`{dry_run}`')
        print('Append Timestamp:'.ljust(23), f'`{append_timestamp}`')
        print('Folder Suffix:'.ljust(23), f'`{folder_suffix}`')
        print('Output directory:'.ljust(23), f'`{out_dir}`')

        for repo in repos:
            repo_final_output = f'  > {build_repo_and_info_str(repo, repo.status.value[1], max_name_len, max_user_len, color=repo.status.value[2])}'
            prints_log.append(repo_final_output)
            print(repo_final_output)
        prints_log.append((''))
        print()
        # TODO: CloneReport should have all above info plus the following pull report string

        if not skip_flag and not dry_run:
            extract_data_folder(out_dir)
            create_vscode_workspace(out_dir, repo_prefix, repos)
        report_str = print_pull_report(students, num_repos, num_not_accepted, num_no_commit, num_cloned, num_reset, ellapsed_time, dry_run, current_pull)
        if debug:
            log_handler.info(report_str)
            for repo in repos:
                log_handler.info(pformat_objects(repo))

        for repo in repos:
            repo_final_output = f'  > {build_repo_and_info_str(repo, repo.status.value[1], max_name_len, max_user_len, color=repo.status.value[2])}'
            prints_log.append(repo_final_output)
        prints_log.append((''))

        prints_log.append(report_str)

        clone_report = CloneReport(repo_prefix, due_date, due_time, datetime.today().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M'), dry_run, students_path, prints_log)

        save_report(clone_report, config_manager)
    except Exception as e:
        if repos_created:
            for repo in repos:
                if repo.status.value[3]:
                    continue
                repo.status = RepoStatus.ERROR
        if debug:
            log_handler.critical(f'Error: {e}')
            log_handler.critical(format_exc())
        raise e
    except KeyboardInterrupt:
        print()
        return
    finally:
        log_handler.close()
        client.close()
        gc.collect()
