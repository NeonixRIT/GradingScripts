import asyncio
import csv
import os
import re
import shutil

from .clone_preset import ClonePreset
from .clone_report import CloneReport
from .student_param import StudentParam

from utils import bool_prompt, run, onerror
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, WHITE, CYAN

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from pprint import pformat
from time import perf_counter
from urllib.parse import urlencode

UTC_OFFSET = datetime.now(timezone.utc).astimezone().utcoffset() // timedelta(hours=1)
CURRENT_TIMEZONE = timezone(timedelta(hours=UTC_OFFSET))


def get_page_by_rel(links: str, rel: str = 'last'):
    val = re.findall(rf'.*&page=(\d+).*>; rel="{rel}"', links)
    if val:
        return int(val[0])
    return None


def get_students(student_filename: str) -> dict:
    """
    Reads class roster csv in the format given by github classroom:
    "identifier","github_username","github_id","name"

    and returns a dictionary of students mapping github username to real name
    """
    students = {}  # student dict
    if Path(student_filename).exists():  # if classroom roster is found
        with open(student_filename) as f_handle:  # use with to auto close file
            csv_reader = csv.reader(f_handle)  # Use csv reader to separate values into a list
            next(csv_reader)  # skip header line
            for student in csv_reader:
                name = re.sub(r'([.]\s?|[,]\s?|\s)', '-', student[0]).replace("'", '-').rstrip(r'-').strip()
                github = student[1].strip()
                if name and github:  # if csv contains student name and github username, map them to each other
                    students[github] = name
    else:
        raise Exception(f'Classroom roster `{student_filename}` does not exist.')
    return students  # return dict mapping names to github usernames


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


def get_time():
    """
    Get assignment due time from input.
    """
    current = False
    time_due = input('Time Due (24hr HH:MM, press `enter` for current): ')  # get time assignment was due
    if not time_due:  # if time due is blank use current time
        current = True
        current_time = datetime.now()  # get current time
        time_due = current_time.strftime('%H:%M')  # format current time into hour:minute 24hr format
        print(f'Using current time: {time_due}')  # output what is being used to end user
    return current, time_due


def get_date():
    """
    Get assignment due date from input.
    """
    current = False
    date_due = input('Date Due (format = yyyy-mm-dd, press `enter` for current): ')  # get due date
    if not date_due:  # If due date is blank use current date
        current = True
        current_date = date.today()  # get current date
        date_due = current_date.strftime('%Y-%m-%d')  # get current date in year-month-day format
        print(f'Using current date: {date_due}')  # output what is being used to end user
    return current, date_due


def check_date(date_inp: str):
    """
    Ensure proper date format
    """
    if not re.match(r'\d{4}-\d{2}-\d{2}', date_inp):
        return False
    return True


class GitHubAPIClient:
    def __init__(self, context, auth_token: str, organization: str) -> None:
        self.__organization = organization
        self.__auth_token = auth_token
        self.context = context
        self.headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {self.__auth_token}',
            'X-GitHub-Api-Version': '2022-11-28',
        }
        if not auth_token:
            del self.headers['Authorization']

        self.repo_params = {'q': f'org:{self.__organization} fork:true', 'per_page': 100}

        self.push_params = {'activity_type': 'push,force_push', 'order': 'desc', 'per_page': 100, 'page': 1}
        self.commit_params = {'per_page': 1, 'page': 1}

        self.assignment_repos = {}
        self.assignment_students_accepted = {}
        self.assignment_students_not_accepted = {}
        self.assignment_students_no_commit = {}
        self.assignment_students_seen = {}
        self.assignment_output_log = {}
        self.assignment_flags = {}

        self.students = None
        self.loaded_csv = None
        if self.context is not None:
            self.students = get_students(self.context.config_manager.config.students_csv)
            self.loaded_csv = self.context.config_manager.config.students_csv
        self.log_file_handler = None
        self.clone_log = []
        self.reset_log = []
        self.current_pull = False
        self.session = None

    def __repr__(self):
        return pformat_objects(self.__dict__).replace(self.context.config_manager.config.token, 'REDACTED')

    def is_authorized(self) -> tuple:
        """
        Check if auth token is valid
        """
        import httpx
        import orjson

        org_url = f'https://api.github.com/orgs/{self.__organization}'
        try:
            response = httpx.get(org_url, headers=self.headers, timeout=10)
            org_auth = orjson.loads(response.content).get('total_private_repos', False)
            if not org_auth:
                return False, response.status_code
        except TimeoutError:
            raise ConnectionError('Connection timed out.') from None
        return True, response.status_code

    async def assignment_exists(self, assignment_name: str) -> tuple:
        """
        Check if assignment exists
        """
        import orjson

        if not assignment_name:
            return True, -1
        params = dict(self.repo_params)
        params['per_page'] = 1
        params['q'] = f'{assignment_name} ' + params['q']
        url = 'https://api.github.com/search/repositories'
        response = await self.__async_request(url, params)
        if response.status_code != 200:
            return 0
        repo_json = orjson.loads(response.content)
        if repo_json.get('total_count', 0) == 0:
            return 0
        return repo_json['total_count']

    def print_and_log(self, message: str, assignment_name: str, color: str = WHITE):
        print(f'{color}{message}{WHITE}')
        self.assignment_output_log[assignment_name].append(message)

    async def __async_request(self, url: str, params: dict = None):
        import httpx

        if self.session is None:
            self.session = httpx.AsyncClient(http1=False, http2=True)

        response = await self.session.get(f'{url}?{urlencode(params)}', headers=self.headers)
        if self.log_file_handler is not None:
            self.log_file_handler.write('*** ASYNC REQUEST ***\n')
            self.log_file_handler.write(f'{pformat_objects(locals())}\n'.replace(self.context.config_manager.config.token, 'REDACTED'))
            self.log_file_handler.write(f'{pformat_objects(response)}\n\n\n'.replace(self.context.config_manager.config.token, 'REDACTED'))
        return response

    async def fetch_all_pages(self, base_url: str, params: dict):
        import orjson

        page = 1
        while True:
            params['page'] = page
            response = await self.__async_request(base_url, params)
            if response.status_code != 200:
                break

            data = orjson.loads(response.content)
            items = None
            if isinstance(data, dict):
                items = data.get('items', [])
            elif isinstance(data, list):
                items = data
            if not items:
                break

            # Yield the entire page's worth of items
            yield items

            # Check if there's another page available
            links = response.headers.get('link', '')
            last_page = get_page_by_rel(links, 'last')
            if not last_page or page >= last_page:
                break
            page += 1

    def __get_adjusted_due_datetime(self, repo, due_date: str, due_time: str) -> tuple:
        pull_flags = self.assignment_flags[repo['assignment_name']]
        is_ca = pull_flags[0]
        is_as = pull_flags[1]
        is_ex = pull_flags[2]
        student_params = StudentParam('', '', 0, 0, 0)
        for student in self.context.config_manager.config.extra_student_parameters:
            if repo['name'].endswith(student.github):
                student_params = student
                break

        hours_adjust = 0
        if is_ca:
            hours_adjust = student_params.class_activity_adj
        elif is_as:
            hours_adjust = student_params.assignment_adj
        elif is_ex:
            hours_adjust = student_params.exam_adj

        date_due_tmp = None
        time_due_tmp = None
        if hours_adjust > 0:
            due_datetime = datetime.strptime(f'{due_date} {due_time}', '%Y-%m-%d %H:%M')
            due_datetime += timedelta(hours=hours_adjust)
            due_datetime_strip = due_datetime.strftime('%Y-%m-%d %H:%M').split(' ')
            date_due_tmp = due_datetime_strip[0]
            time_due_tmp = due_datetime_strip[1]
        else:
            date_due_tmp = due_date
            time_due_tmp = due_time

        due_datetime = datetime.strptime(f'{date_due_tmp} {time_due_tmp}', '%Y-%m-%d %H:%M') - timedelta(hours=UTC_OFFSET)  # convert to UTC
        time_diff = due_datetime.hour - due_datetime.astimezone(CURRENT_TIMEZONE).hour  # check if current time's Daylight Savings Time is different from due date/time
        is_dst_diff = time_diff != 0
        if is_dst_diff:
            due_datetime -= timedelta(hours=time_diff)
        # want to get pushes that happened before due date/time, so add a minute to due date/time
        due_datetime = due_datetime + timedelta(minutes=1)
        return due_datetime

    def __get_commit_from_pushes(self, due_datetime: datetime, pushes: dict) -> str:
        for push in pushes:
            push_time = datetime.strptime(push['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
            if push_time < due_datetime:
                return push['after']
        return None

    async def __get_pushed_count_fast(self, repo) -> int:
        import orjson

        params = dict(self.push_params)
        url = f'{repo["url"]}/activity'
        response = await self.__async_request(url, params)
        if response.status_code != 200:
            return -1
        pushes = orjson.loads(response.content)
        return len(pushes)

    async def __get_push_info(self, repo, due_date, due_time) -> tuple[str, int]:
        # TODO: Support github classroom team repos, owned by the org, check "teams_url", and then "members_url" in repo json to get students in team
        params = dict(self.push_params)
        # params['actor'] = repo['student_github']

        due_datetime = self.__get_adjusted_due_datetime(repo, due_date, due_time)  # adjust based on student parameters, Timezone, and DST
        # GitHub API {owner}/{repo}/activity endpoint allows to query all pushes for a repo by a user
        url = f'{repo["url"]}/activity'
        num_pushes = 0
        async for pushes in self.fetch_all_pages(url, params):
            num_pushes += len(pushes)
            commit_hash = self.__get_commit_from_pushes(due_datetime, pushes)
            if commit_hash is not None:
                return commit_hash, num_pushes
        return None, num_pushes

    async def _validate_repo_fields(self, repo: dict, due_date: str, due_time: str) -> dict | None:
        """
        Checks commit/push information for the given repo.
        Returns the repo dict if it's valid, or None if it's invalid or has no commits.
        """
        student_name = repo['student_name']
        student_github = repo['student_github']

        # Decide which push info method to call
        if not self.current_pull:
            commit_hash, push_count = await self.__get_push_info(repo, due_date, due_time)
        else:
            # "Fast" approach: just check how many pushes exist
            push_count = await self.__get_pushed_count_fast(repo)
            commit_hash = '-1'  # Assign a default to indicate "current pull"

        repo['due_commit_hash'] = commit_hash

        # If push_count <= 0, no commits exist in the repo
        if push_count <= 0:
            self.assignment_students_no_commit[repo['assignment_name']].add((student_name, student_github))
            return None

        # If there's no valid commit before due date/time, treat as not accepted
        if commit_hash is None:
            self.assignment_students_not_accepted[repo['assignment_name']].add((student_name, student_github))
            return None

        # Otherwise, repo is valid
        return repo

    async def __add_valid_repos(self, assignment_name: str, due_date: str, due_time: str, repos: list[dict]) -> None:
        """
        Filters and validates a list of repo dictionaries, ensuring they:
        1. Belong to a student in self.students.
        2. Have a valid commit hash before the due date/time (unless we're in current_pull mode).
        3. Actually have commits (push_count > 0).

        Valid repos are appended to self.assignment_repos[assignment_name].
        """
        tasks = []
        for repo in repos:
            # 1. Filter out repos whose 'name' doesn't match a known student
            student_github = repo['name'].replace(f'{assignment_name}-', '')
            if student_github not in self.students:
                continue

            # 2. Populate needed fields
            student_name = self.students[student_github]
            repo['student_name'] = student_name
            repo['student_github'] = student_github
            repo['new_name'] = repo['name'].replace(student_github, student_name)
            repo['assignment_name'] = assignment_name

            # Track this student as having accepted (until proven otherwise)
            self.assignment_students_accepted[assignment_name].add((student_name, student_github))

            # 3. Schedule a task to validate commit/push info for each repo
            tasks.append(asyncio.create_task(self._validate_repo_fields(repo, due_date, due_time)))

        # 4. Run all validations concurrently
        validated_repos = await asyncio.gather(*tasks)

        # 5. Append valid repos to our assignment_repos list
        for valid_repo in validated_repos:
            # _validate_repo_fields returns None if invalid
            if valid_repo is None:
                continue
            self.assignment_students_seen[assignment_name].add((valid_repo['student_name'], valid_repo['student_github']))
            self.assignment_repos[assignment_name].append(valid_repo)

    async def __rollback_repo(self, repo):
        """
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        """
        try:
            # run process on system that executes 'git reset' command. stdout is redirected so it doesn't output to end user
            # git reset is similar to checkout but doesn't care about detached heads and is more forceful
            # cmd = f'git reset --hard {repo["due_commit_hash"]}'
            cmd = ['git', 'reset', '--hard', repo['due_commit_hash']]
            stdout, stderr, exitcode = await run(cmd, repo['local_path'])
            if self.context.config_manager.config.debug:
                self.reset_log.append(f'*** ROLLBACK REPO [{repo["name"]}] ***\n{stdout}\n{stderr}\n{exitcode=}\n')
            repo['is_rolled_back'] = True
        except Exception:
            self.print_and_log(
                f'{LIGHT_RED}[{repo["name"]}] Rollback Failed: Likely invalid filename at commit `{repo["due_commit_hash"]}`.{WHITE}',
                repo['assignment_name'],
            )

    async def get_repos(self, assignment_name: str, due_date: str, due_time: str, refresh: bool = False):
        """
        Return all repos that have at least one commit before due date/time
        and are from students in class roster and are only for the desired assignment
        """
        params = dict(self.repo_params)
        if assignment_name in self.assignment_repos and not refresh:
            return self.assignment_repos[assignment_name]

        if assignment_name:
            params['q'] = f'{assignment_name} ' + params['q']

        self.assignment_repos[assignment_name] = []
        self.assignment_students_accepted[assignment_name] = set()
        self.assignment_students_not_accepted[assignment_name] = set()
        self.assignment_students_no_commit[assignment_name] = set()
        self.assignment_students_seen[assignment_name] = set()
        self.assignment_output_log[assignment_name] = []

        url = 'https://api.github.com/search/repositories'
        async for repos in self.fetch_all_pages(url, params):
            await self.__add_valid_repos(assignment_name, due_date, due_time, repos)
            if len(self.assignment_students_seen[assignment_name]) == len(self.students):
                break

        for student_github in self.students:
            student_tuple = (self.students[student_github], student_github)
            if student_tuple not in self.assignment_students_accepted[assignment_name]:
                self.assignment_students_not_accepted[assignment_name].add((self.students[student_github], student_github))
        return self.assignment_repos[assignment_name]

    async def __clone_repo(self, repo: dict, path: Path) -> None:
        """
        Clones the given repo into `path / repo["new_name"]`.
        If clone is successful and `self.current_pull` is False (and not dry_run),
        attempts to roll back the repo to the due date/time commit hash.
        """
        destination_path = str(Path(path) / repo['new_name'])
        self.print_and_log(
            f'    > Cloning [{repo["name"]}] {repo["new_name"]}...',
            repo['assignment_name'],
        )

        # 1. Build the git clone command
        cmd = self._build_clone_cmd(repo, destination_path)

        # 2. If dry_run, skip the actual clone
        if self.context.dry_run:
            repo['local_path'] = destination_path
            return

        # 3. Attempt the clone (with automatic retry on failure)
        success = await self._attempt_clone(repo, cmd)

        # 4. If clone fails or we’re in a current pull, do nothing else
        if not success or self.current_pull:
            repo['local_path'] = destination_path
            return

        # 5. Otherwise, roll back the repo
        repo['local_path'] = destination_path
        await self.__rollback_repo(repo)

    def _build_clone_cmd(self, repo: dict, destination_path: str) -> list[str]:
        """
        Returns a list containing the git clone command.
        Injects the auth token and decides whether to clone shallow (--depth=1) or not.
        """
        clone_url = repo['clone_url'].replace('https://', f'https://{self.__auth_token}@')
        base_cmd = ['git', 'clone', '--single-branch']

        if self.current_pull:
            # Shallow clone if pulling 'current' state
            base_cmd.extend(['--depth', '1'])

        base_cmd.extend([clone_url, destination_path])
        return base_cmd

    async def _attempt_clone(self, repo: dict, cmd: list[str]) -> bool:
        """
        Attempts to clone the repo. If it fails, retries once automatically,
        then repeatedly prompts the user if they'd like to retry again.
        Logs output if debug is enabled.
        Returns True if the clone eventually succeeds, False otherwise.
        """
        max_automatic_retries = 1

        for i in range(max_automatic_retries + 1):
            success = await self._run_clone_command(repo, cmd)
            if success:
                return True
            # If this wasn't the last automatic retry, keep going
            if i < max_automatic_retries:
                continue

            # Prompt the user for further retries if the clone continues failing
            while True:
                if not bool_prompt('Would you like to retry?', True):
                    return False
                if await self._run_clone_command(repo, cmd):
                    return True

        return False  # If we somehow exit the loop without success

    async def _run_clone_command(self, repo: dict, cmd: list[str]) -> bool:
        """
        Executes the git clone command once. Returns True if successful, False otherwise.
        Logs stdout/stderr if debug is enabled.
        """
        stdout, stderr, exitcode = await run(cmd)
        if self.context.config_manager.config.debug:
            self.clone_log.append(f'*** CLONE REPO [{repo["name"]}] ***\n{stdout}\n{stderr}\nexitcode={exitcode}\n')

        if exitcode != 0:
            # Print the error on the last forced attempt
            self.print_and_log(
                f'{LIGHT_RED}[{repo["name"]}] Clone Failed:\n{stderr}\n{WHITE}',
                repo['assignment_name'],
            )
            return False

        return True

    async def pull_assignment_repos(self, assignment_name: str, path: Path | str):
        """
        Clones and roles back all repos for a given assignment to the due date/time
        """
        if assignment_name not in self.assignment_repos:
            raise KeyError(f'Assignment `{assignment_name}` not found. Please run `get_repos` first')
        for student in self.assignment_students_not_accepted[assignment_name]:
            self.print_and_log(
                f'    > {LIGHT_RED}Skipping [{student[1]}] {student[0]}: Assignment not accepted before due date/time.{WHITE}',
                assignment_name,
            )
        for student in self.assignment_students_no_commit[assignment_name]:
            self.print_and_log(
                f'    > {LIGHT_RED}Skipping [{student[1]}] {student[0]}: Repo has no commits.{WHITE}',
                assignment_name,
            )
        tasks = []
        for repo in self.assignment_repos[assignment_name]:
            task = asyncio.ensure_future(self.__clone_repo(repo, path))
            tasks.append(task)
        await asyncio.gather(*tasks)

    def print_pull_report(self, assignment_name, exec_time: float) -> str:
        """
        Give end-user somewhat detailed report of what repos were able to be cloned, how many students accepted the assignments, etc.
        """
        done_str = f'{LIGHT_GREEN}Done in {round(exec_time, 2)} seconds.{WHITE}'
        total_assignment_repos = len(self.assignment_repos[assignment_name])

        num_not_accepted = len(self.assignment_students_not_accepted[assignment_name])
        num_accepted = len(self.students) - num_not_accepted
        section_students = len(self.students)
        accept_str = f'{LIGHT_GREEN}{num_accepted}{WHITE}' if num_accepted == section_students else f'{LIGHT_RED}{num_accepted}{WHITE}'
        full_accept_str = f'{accept_str}{LIGHT_GREEN}/{len(self.students)} accepted the assignment before due datetime.{WHITE}'

        num_no_commits = len(self.assignment_students_no_commit[assignment_name])
        commits_str = f'{LIGHT_GREEN}{num_no_commits}{WHITE}' if num_no_commits == 0 else f'{LIGHT_RED}{num_no_commits}{WHITE}'
        full_commits_str = f'{commits_str}{LIGHT_GREEN}/{num_accepted} had no commits.'

        cloned_num = 0
        rolled_back_num = 0
        for repo in self.assignment_repos[assignment_name]:
            if repo.get('local_path', False):
                cloned_num += 1
            if repo.get('is_rolled_back', False):
                rolled_back_num += 1

        clone_str = f'{LIGHT_GREEN}{cloned_num}{WHITE}' if cloned_num == total_assignment_repos else f'{LIGHT_RED}{cloned_num}{WHITE}'
        full_clone_str = f'{LIGHT_GREEN}Cloned {clone_str}{LIGHT_GREEN}/{total_assignment_repos} repos.{WHITE}'

        rolled_back_str = f'{LIGHT_GREEN}{rolled_back_num}{WHITE}' if rolled_back_num == cloned_num else f'{LIGHT_RED}{rolled_back_num}{WHITE}'
        full_rolled_back_str = f'{LIGHT_GREEN}Rolled back {rolled_back_str}{LIGHT_GREEN}/{cloned_num} repos.{WHITE}'

        print()
        print(done_str)
        print(full_accept_str)
        print(full_commits_str)
        print(full_clone_str)
        if not self.context.dry_run or not self.current_pull:
            print(full_rolled_back_str)
        print()

        full_report_str = f'\n{done_str}\n{full_accept_str}\n{full_commits_str}\n{full_clone_str}\n{full_rolled_back_str}'
        return full_report_str

    async def attempt_get_assignment(self):
        """
        Get assignment name from input. Does not accept empty input.
        """
        assignment_name = input('Assignment Name: ')  # get assignment name (repo prefix)
        repo_count = await self.assignment_exists(assignment_name)
        while not assignment_name or not repo_count:  # if input is empty ask again
            if assignment_name == 'quit()':
                return assignment_name
            if not repo_count:
                print(f'Assignment `{assignment_name}` not found. Please try again.')
            assignment_name = input('Please input an assignment name: ')
            repo_count = await self.assignment_exists(assignment_name)
        return assignment_name

    async def save_report(self, report):
        clone_logs = self.context.config_manager.config.clone_history
        clone_logs.append(report)
        if len(clone_logs) > 8:
            clone_logs = clone_logs[1:]
        self.context.config_manager.set_config_value('clone_history', clone_logs)

    async def create_vscode_workspace(self, assignment_name, parent_folder_path):
        workspace_path = Path(parent_folder_path) / f'{assignment_name}.code-workspace'
        with open(workspace_path, 'w') as f:
            f.write('{\n')
            f.write('    "folders": [\n')
            for repo in sorted(list(self.assignment_repos[assignment_name]), key=lambda x: x['new_name']):
                val = repo['new_name']
                f.write(f'        {{ "path": "{val}" }},\n')
            f.write('    ],\n\t"settings": {}\n')
            f.write('}\n')
        self.print_and_log(
            f'{LIGHT_GREEN}VSCode workspace file created at {workspace_path}.{WHITE}',
            assignment_name,
        )

    async def extract_data_folder(self, assignment_name, initial_path, data_folder_name='data'):
        repos = os.listdir(initial_path)
        repo_to_check = repos[len(repos) - 1]
        folders = os.listdir(Path(initial_path) / repo_to_check)
        if data_folder_name in folders:
            shutil.copytree(f'{str(Path(initial_path) / repo_to_check / data_folder_name)}', f'{str(Path(initial_path) / data_folder_name)}')
            self.print_and_log(
                f'{LIGHT_GREEN}Data folder extracted to the output directory.{WHITE}',
                assignment_name,
            )

    async def run(self, preset: ClonePreset = None):
        students_start = perf_counter()
        students_path = self.context.config_manager.config.students_csv
        if self.loaded_csv is None or self.students is None:
            self.students = get_students(students_path)
            self.loaded_csv = students_path
        if preset is None:
            preset = ClonePreset('', '', '', students_path, False, (0, 0, 0))
            preset.append_timestamp = bool_prompt(
                'Append timestamp to repo folder name?',
                not self.context.config_manager.config.replace_clone_duplicates,
            )
        if self.loaded_csv != preset.csv_path:
            self.students = get_students(preset.csv_path)
            self.loaded_csv = preset.csv_path
        students_stop = perf_counter()
        students_time = students_stop - students_start

        assignment_name = await self.attempt_get_assignment()  # prompt and verify assignment name
        if assignment_name == 'quit()':
            return
        # due_tag = ''
        # if self.clone_via_tag:
        #     due_tag = attempt_get_tag()

        #     if preset.append_timestamp:
        #         preset.folder_suffix += f'_{due_tag}'

        flags = preset.clone_type  # (class activity, assignment, exam)
        if preset.clone_type is None:
            for param in self.context.config_manager.config.extra_student_parameters:
                if param.github in self.students:
                    print(f'{LIGHT_GREEN}Student found in extra parameters.{WHITE}')
                    res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ')
                    while res != 'ca' and res != 'as' and res != 'ex':
                        res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ')
                    if res == 'ca':
                        flags = (1, 0, 0)
                    elif res == 'as':
                        flags = (0, 1, 0)
                    elif res == 'ex':
                        flags = (0, 0, 1)
                    break

        self.assignment_flags[assignment_name] = flags

        due_date = ''
        # if not self.clone_via_tag:
        time_is_current = False
        if not preset.clone_time:
            time_is_current, preset.clone_time = get_time()

        date_is_current, due_date = get_date()
        while not check_date(due_date):
            due_date = get_date()

        if date_is_current and time_is_current:
            self.current_pull = True

        if preset.append_timestamp:
            date_str = due_date[4:].replace('-', '_')
            time_str = preset.clone_time.replace(':', '_')
            preset.folder_suffix += f'_{date_str}_{time_str}'
        # end if

        pull_start_1 = perf_counter()
        i = 0
        parent_folder_path = f'{self.context.config_manager.config.out_dir}/{assignment_name}{preset.folder_suffix}'  # prompt parent folder (IE assingment_name-AS in config.out_dir)
        while Path(parent_folder_path).exists() and not self.context.config_manager.config.replace_clone_duplicates:
            i += 1
            parent_folder_path = f'{self.context.config_manager.config.out_dir}/{assignment_name}{preset.folder_suffix}_iter_{i}'

        if Path(parent_folder_path).exists() and self.context.config_manager.config.replace_clone_duplicates:
            if self.context.dry_run:
                num_files = len(os.listdir(parent_folder_path))
                print(f'{CYAN}[INFO]: Would have deleted {num_files} files/folders in {parent_folder_path}.{WHITE}')
            else:
                num_files = len(os.listdir(parent_folder_path))
                print(f'{CYAN}[INFO]: Will delete {num_files} files/folders in {parent_folder_path}.{WHITE}')
                for folder in os.listdir(parent_folder_path):
                    if (Path(parent_folder_path) / folder).is_dir():
                        shutil.rmtree(Path(parent_folder_path) / folder, onexc=onerror)
                    else:
                        os.remove(Path(parent_folder_path) / folder)

        if not self.context.dry_run and not Path(parent_folder_path).exists():
            os.mkdir(parent_folder_path)
        pull_stop_1 = perf_counter()

        if self.context.config_manager.config.debug:
            self.log_file_handler = open(str(Path(parent_folder_path) / 'log.txt'), 'w')
            self.log_file_handler.write(f'*** Globals ***\n{pformat_objects(globals())}\n\n\n*** Locals ***\n{pformat_objects(locals())}*** Clone Details ***\n'.replace(self.context.config_manager.config.token, 'REDACTED'))
        skip_flag = False
        while True:
            pull_start_2 = perf_counter()
            repos = await self.get_repos(assignment_name, due_date, preset.clone_time, refresh=True)  # get repos for assignment
            pull_stop_2 = perf_counter()
            if len(repos) > 0:
                break
            if len(repos) == 0 and (len(self.assignment_students_no_commit) > 0 or len(self.assignment_students_not_accepted) > 0):
                skip_flag = True
                break
            print(f'{LIGHT_RED}No students have accepted the assignment `{assignment_name}`.{WHITE}')
            print('Please try again or type `quit()` to return to the clone menu.')
            tmp_flags = self.assignment_flags[assignment_name]
            del self.assignment_flags[assignment_name]
            del self.assignment_repos[assignment_name]
            del self.assignment_students_accepted[assignment_name]
            del self.assignment_students_not_accepted[assignment_name]
            del self.assignment_students_no_commit[assignment_name]
            del self.assignment_output_log[assignment_name]
            assignment_name = await self.attempt_get_assignment()
            if assignment_name == 'quit()':
                return
            self.assignment_flags[assignment_name] = tmp_flags

        print()

        pull_start_3 = perf_counter()
        outdir = parent_folder_path[len(self.context.config_manager.config.out_dir) + 1 :]
        outdir_str = f'Output directory: {outdir}'
        self.print_and_log(outdir_str, assignment_name)
        await self.pull_assignment_repos(assignment_name, parent_folder_path)
        if not skip_flag and not self.context.dry_run:
            await self.extract_data_folder(assignment_name, parent_folder_path)
        pull_stop_3 = perf_counter()
        pull_time = (pull_stop_3 - pull_start_3) + (pull_stop_2 - pull_start_2) + (pull_stop_1 - pull_start_1)

        ellapsed_time = pull_time + students_time
        end_report_str = self.print_pull_report(assignment_name, ellapsed_time)
        self.assignment_output_log[assignment_name].append(end_report_str)
        if not skip_flag and not self.context.dry_run:
            await self.create_vscode_workspace(assignment_name, parent_folder_path)

        report = CloneReport(
            assignment_name,
            due_date,
            preset.clone_time,
            datetime.today().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M'),
            self.context.dry_run,
            str(students_path),
            tuple(self.assignment_output_log[assignment_name]),
        )

        self.current_pull = False
        await self.save_report(report)

        if self.log_file_handler is not None and self.context.config_manager.config.debug:
            self.log_file_handler.writelines(self.clone_log)
            self.log_file_handler.writelines(self.reset_log)

        del self.assignment_repos[assignment_name]
        del self.assignment_students_accepted[assignment_name]
        del self.assignment_students_not_accepted[assignment_name]
        del self.assignment_students_no_commit[assignment_name]
        del self.assignment_output_log[assignment_name]
        del self.assignment_flags[assignment_name]
        del self.assignment_students_seen[assignment_name]
        self.clone_log = []
        self.reset_log = []
        await self.session.aclose()
        if self.log_file_handler is not None:
            self.log_file_handler.close()
        self.log_file_handler = None
        self.session = None
