import asyncio
import csv
import os
import re
import shutil

from .clone_preset import ClonePreset
from .clone_report import CloneReport
from .student_param import StudentParam

from utils import bool_prompt, run
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, WHITE

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlencode

LOG_FILE_PATH = './data/logs.log'
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


def get_time():
    """
    Get assignment due time from input.
    """
    time_due = input('Time Due (24hr, press `enter` for current): ')  # get time assignment was due
    if not time_due:  # if time due is blank use current time
        current_time = datetime.now()  # get current time
        time_due = current_time.strftime('%H:%M')  # format current time into hour:minute 24hr format
        print(f'Using current time: {time_due}')  # output what is being used to end user
    return time_due


def get_date():
    """
    Get assignment due date from input.
    """
    date_due = input('Date Due (format = yyyy-mm-dd, press `enter` for current): ')  # get due date
    if not date_due:  # If due date is blank use current date
        current_date = date.today()  # get current date
        date_due = current_date.strftime('%Y-%m-%d')  # get current date in year-month-day format
        print(f'Using current date: {date_due}')  # output what is being used to end user
    return date_due


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

        self.repo_params = {'q': f'org:{self.__organization}', 'per_page': 100}

        self.commit_params = {'per_page': 1, 'page': 1}

        self.assignment_repos = {}
        self.assignment_students_accepted = {}
        self.assignment_students_not_accepted = {}
        self.assignment_students_no_commit = {}
        self.assignment_output_log = {}
        self.assignment_flags = {}

        self.students = None
        self.loaded_csv = None
        if self.context is not None:
            self.students = get_students(self.context.config_manager.config.students_csv)
            self.loaded_csv = self.context.config_manager.config.students_csv

    def is_authorized(self) -> tuple:
        """
        Check if auth token is valid
        """
        import requests

        org_url = f'https://api.github.com/orgs/{self.__organization}'
        try:
            response = requests.get(org_url, headers=self.headers, timeout=10)
            org_auth = getattr(
                response.json(object_hook=lambda d: SimpleNamespace(**d)),
                'total_private_repos',
                False,
            )
            if not org_auth:
                return False, response.status_code
        except TimeoutError:
            raise ConnectionError('Connection timed out.') from None
        return True, response.status_code

    async def assignment_exists(self, assignment_name: str) -> tuple:
        """
        Check if assignment exists
        """
        if not assignment_name:
            return True, -1
        params = dict(self.repo_params)
        params['per_page'] = 1
        params['q'] = f'{assignment_name} ' + params['q']
        url = 'https://api.github.com/search/repositories'
        response = await self.__async_request(url, params)
        if response.status_code != 200:
            return False, 0
        repo_json = response.json(object_hook=lambda d: SimpleNamespace(**d))
        if getattr(repo_json, 'total_count', 0) == 0:
            return False, 0
        return True, repo_json.total_count

    def print_and_log(self, message: str, assignment_name: str, color: str = WHITE):
        print(f'{color}{message}{WHITE}')
        self.assignment_output_log[assignment_name].append(message)

    async def __async_request(self, url: str, params: dict = None):
        import requests

        return requests.get(f'{url}?{urlencode(params)}', headers=self.headers)

    def __get_adjusted_due_datetime(self, repo, due_date: str, due_time: str) -> tuple:
        pull_flags = self.assignment_flags[repo.assignment_name]
        is_ca = pull_flags[0]
        is_as = pull_flags[1]
        is_ex = pull_flags[2]
        student_params = StudentParam('', '', 0, 0, 0)
        for student in self.context.config_manager.config.extra_student_parameters:
            if repo.name.endswith(student.github):
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
        return date_due_tmp, time_due_tmp

    async def __get_commit_info(self, repo, due_date, due_time):
        params = dict(self.commit_params)
        if not due_date:
            pass
        if not due_time:
            pass
        due_date, due_time = self.__get_adjusted_due_datetime(repo, due_date, due_time)
        due_datetime = datetime.strptime(f'{due_date} {due_time}', '%Y-%m-%d %H:%M') - timedelta(hours=UTC_OFFSET)
        time_diff = due_datetime.hour - due_datetime.astimezone(CURRENT_TIMEZONE).hour
        is_dst_diff = time_diff != 0
        if is_dst_diff:
            due_datetime -= timedelta(hours=time_diff)
        params['until'] = due_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
        response = await self.__async_request(repo.commits_url[:-6], params)
        if response.status_code != 200:
            return None, None
        commit_json = response.json(object_hook=lambda d: SimpleNamespace(**d))
        if not commit_json:
            return None, None
        commit_hash = getattr(commit_json[0], 'sha', None)
        commit_num = get_page_by_rel(response.headers['link'], 'last') if 'link' in response.headers else 1
        return commit_hash, commit_num

    async def __poll_repos_page(self, params: dict, page: int):
        params['page'] = page
        url = f'https://api.github.com/search/repositories?{urlencode(params)}'
        response = await self.__async_request(url, params)
        if response.status_code != 200:
            return False
        return response.json(object_hook=lambda d: SimpleNamespace(**d)).items

    async def __add_valid_repos(self, assignment_name: str, due_date: str, due_time: str, repos: list):
        for repo in repos:
            student_github = repo.name.replace(f'{assignment_name}-', '')
            if student_github not in self.students:
                continue
            student_name = self.students[student_github]
            repo.student_name = student_name
            repo.student_github = student_github
            repo.new_name = repo.name.replace(student_github, student_name)
            repo.assignment_name = assignment_name
            self.assignment_students_accepted[assignment_name].add((student_name, student_github))
            commit_hash, commit_count = await self.__get_commit_info(repo, due_date, due_time)
            repo.due_commit_hash = commit_hash
            repo.due_commit_count = commit_count
            if commit_hash is None or commit_count is None:
                self.assignment_students_not_accepted[assignment_name].add((student_name, student_github))
                continue
            if commit_count <= 1:
                self.assignment_students_no_commit[assignment_name].add((student_name, student_github))
                continue
            self.assignment_repos[assignment_name].append(repo)

    async def __rollback_repo(self, repo):
        """
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        """
        try:
            # run process on system that executes 'git reset' command. stdout is redirected so it doesn't output to end user
            # git reset is similar to checkout but doesn't care about detached heads and is more forceful
            cmd = f'git reset --hard {repo.due_commit_hash}'
            if not self.context.dry_run:
                await run(cmd, repo.local_path)
            repo.is_rolled_back = True
        except Exception:
            self.print_and_log(
                f'{LIGHT_RED}[{repo.name}] Rollback Failed: Likely invalid filename at commit `{repo.due_commit_hash}`.{WHITE}',
                repo.assignment_name,
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
        self.assignment_output_log[assignment_name] = []
        url = 'https://api.github.com/search/repositories'
        response = await self.__async_request(url, params)
        if response.status_code != 200:
            return response.status_code  # raise error based on code
        page_limit = 1
        if 'link' in response.headers:
            page_limit = get_page_by_rel(response.headers['link'], 'last')

        repos = response.json(object_hook=lambda d: SimpleNamespace(**d)).items
        await self.__add_valid_repos(assignment_name, due_date, due_time, repos)
        for page in range(2, page_limit + 1):
            repos = await self.__poll_repos_page(params, page)
            await self.__add_valid_repos(assignment_name, due_date, due_time, repos)

        for student_github in self.students:
            student_tuple = (self.students[student_github], student_github)
            if student_tuple not in self.assignment_students_accepted[assignment_name]:
                self.assignment_students_not_accepted[assignment_name].add((self.students[student_github], student_github))
        return self.assignment_repos[assignment_name]

    async def __clone_repo(self, repo, path: Path):
        destination_path = f'{path}/{repo.new_name}'
        clone_str = f'    > Cloning [{repo.name}] {repo.new_name}...'
        self.print_and_log(clone_str, repo.assignment_name)  # tell end user what repo is being cloned and where it is going to
        # outputs_log.append(clone_str)
        # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user
        clone_url = repo.clone_url.replace('https://', f'https://{self.__auth_token}@')
        cmd = f'git clone --single-branch {clone_url} "{destination_path}"'  # if not due_tag else f'git clone --branch {due_tag} --single-branch {clone_url} "{destination_path}"'
        if not self.context.dry_run:
            await run(cmd)
        repo.local_path = destination_path
        await self.__rollback_repo(repo)

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
            if getattr(repo, 'local_path', False):
                cloned_num += 1
            if getattr(repo, 'is_rolled_back', False):
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
        print(full_rolled_back_str)
        print()

        full_report_str = f'\n{done_str}\n{full_accept_str}\n{full_commits_str}\n{full_clone_str}\n{full_rolled_back_str}'
        return full_report_str

    async def attempt_get_assignment(self):
        """
        Get assignment name from input. Does not accept empty input.
        """
        assignment_name = input('Assignment Name: ')  # get assignment name (repo prefix)
        assignment_exists, _ = await self.assignment_exists(assignment_name)
        while not assignment_name or not assignment_exists:  # if input is empty ask again
            if assignment_name == 'quit()':
                return assignment_name
            print(assignment_name, assignment_exists)
            if not assignment_exists:
                print(f'Assignment `{assignment_name}` not found. Please try again.')
            assignment_name = input('Please input an assignment name: ')
            assignment_exists = await self.assignment_exists(assignment_name)
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
            for repo in self.assignment_repos[assignment_name]:
                f.write(f'        {{ "path": "{repo.new_name}" }},\n')
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
            shutil.move(
                f'{str(Path(initial_path) / repo_to_check)}/{data_folder_name}',
                initial_path,
            )
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
        if not preset.clone_time:
            preset.clone_time = get_time()

        due_date = get_date()
        while not check_date(due_date):
            due_date = get_date()

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

        if Path(parent_folder_path).exists() and self.context.config_manager.config.replace_clone_duplicates and not self.context.dry_run:
            for folder in os.listdir(parent_folder_path):
                if (Path(parent_folder_path) / folder).is_dir():
                    shutil.rmtree(Path(parent_folder_path) / folder)
                else:
                    os.remove(Path(parent_folder_path) / folder)

        if not self.context.dry_run and not Path(parent_folder_path).exists():
            os.mkdir(parent_folder_path)
        pull_stop_1 = perf_counter()

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

        await self.save_report(report)
        del self.assignment_repos[assignment_name]
        del self.assignment_students_accepted[assignment_name]
        del self.assignment_students_not_accepted[assignment_name]
        del self.assignment_students_no_commit[assignment_name]
        del self.assignment_output_log[assignment_name]
        del self.assignment_flags[assignment_name]
