import asyncio
import csv
import itertools
import re
import shutil
import time
import os
import threading
from typing import Iterable

from .clone_preset import ClonePreset
from .clone_report import CloneReport
from .student_param import StudentParam

from utils import get_color_from_bool, bool_prompt, run, list_to_multi_clone_presets
from tuiframeworkpy import SubMenu, Event, MenuOption
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, CYAN, WHITE

from datetime import date, datetime, timedelta
from pathlib import Path


LOG_FILE_PATH = './data/logs.log'


class ReposStruct:
    __slots__ = ['repos_w_students']

    def __init__(self):
        pass


class CloneMenu(SubMenu):
    __slots__ = ['students', 'loaded_csv', 'client', 'repos', 'filtered_repos', 'cloned_repos', 'no_commits_tuples', 'no_commits_students', 'local_options', 'preset_options', 'clone_via_tag', 'parameters', 'outputs_log']

    def __init__(self, id):
        self.client = None
        self.repos = None
        self.students = None
        self.loaded_csv = None

        self.filtered_repos = set()
        self.cloned_repos = None  # async queue
        self.no_commits_tuples = set()
        self.no_commits_students = set()
        self.local_options = []
        self.preset_options = []
        self.clone_via_tag = False

        self.parameters = dict()
        self.outputs_log = []

        manage_presets = MenuOption(1, 'Manage Presets', Event(), Event(), Event(), pause=False)
        manage_presets.on_exit += self.load
        self.local_options.append(manage_presets)

        toggle_clone_tag_event = Event()
        toggle_clone_tag_event += self.toggle_clone_via_tag
        toggle_clone_tag_event += self.load
        toggle_clone_tag = MenuOption(2, f'Clone Via Tag: {get_color_from_bool(self.clone_via_tag)}{self.clone_via_tag}{WHITE}', toggle_clone_tag_event, Event(), Event(), pause=False)
        self.local_options.append(toggle_clone_tag)

        clone_history = MenuOption(3, 'Clone History', Event(), Event(), Event(), pause=False)
        clone_history.on_exit += self.load
        self.local_options.append(clone_history)

        clone_repos_event = Event()
        clone_repos_event += self.clone_repos
        clone_repos = MenuOption(4, 'Continue Without Preset', clone_repos_event, Event(), Event())
        self.local_options.append(clone_repos)

        SubMenu.__init__(self, id, 'Clone Presets', self.preset_options + self.local_options, Event(), Event(), preload=False)
        self.on_enter += self.load

    def load(self):
        self.client = self.parent.client
        self.repos = self.parent.repos
        self.students = self.parent.students
        self.loaded_csv = self.context.config_manager.config.students_csv

        self.preset_options = self.build_preset_options()
        for i, option in enumerate(self.local_options):
            option.number = len(self.preset_options) + i + 1
            if option.text.startswith('Clone Via Tag: '):
                option.text = f'Clone Via Tag: {get_color_from_bool(self.clone_via_tag)}{self.clone_via_tag}{WHITE}'
        options = self.preset_options + self.local_options
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.prompt_string = self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '

    def toggle_clone_via_tag(self):
        self.clone_via_tag = not self.clone_via_tag

    def save_report(self, report):
        clone_logs = self.context.config_manager.config.clone_history
        clone_logs.append(report)
        if len(clone_logs) > 8:
            clone_logs = clone_logs[1:]
        self.context.config_manager.set_config_value('clone_history', clone_logs)

    def clone_repos(self, preset: ClonePreset = None):
        students_path = self.context.config_manager.config.students_csv
        if preset is not None and self.loaded_csv != preset.csv_path:
            students_path = preset.csv_path
            self.students = get_students(students_path)
            self.loaded_csv = preset.csv_path
        if students_path != self.loaded_csv:
            self.students = get_students(students_path)
            self.loaded_csv = students_path
        if preset is None:
            preset = ClonePreset('', '', '', students_path, False)
            preset.append_timestamp = bool_prompt('Append timestamp to repo folder name?\nIf using a tag name, it will append the tag instead', True)

        assignment_name = attempt_get_assignment()  # prompt assignment name
        assignment_name, self.filtered_repos = verify_assignment_name(assignment_name, self.repos)

        due_tag = ''
        if self.clone_via_tag:
            due_tag = attempt_get_tag()

            if preset.append_timestamp:
                preset.folder_suffix += f'_{due_tag}'

        flags = (0, 0, 0)  # (class activity, assignment, exam)
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

        repos_struct = ReposStruct()
        thread = threading.Thread(target=lambda: self.get_repos_specified_students(self.filtered_repos, assignment_name, due_tag, repos_struct))  # noqa: F821
        thread.start()

        due_date = ''
        if not self.clone_via_tag:
            if not preset.clone_time:
                preset.clone_time = get_time()

            due_date = get_date()
            while not check_date(due_date):
                due_date = get_date()

            if preset.append_timestamp:
                date_str = due_date[4:].replace('-', '_')
                time_str = preset.clone_time.replace(':', '_')
                preset.folder_suffix += f'_{date_str}_{time_str}'

        start = time.perf_counter()
        parent_folder_path = f'{self.context.config_manager.config.out_dir}/{assignment_name}{preset.folder_suffix}' # prompt parent folder (IE assingment_name-AS in config.out_dir)

        i = 0
        while Path(parent_folder_path).exists():
            i += 1
            parent_folder_path = f'{self.context.config_manager.config.out_dir}/{assignment_name}{preset.folder_suffix}_iter_{i}'

        os.mkdir(parent_folder_path)
        thread.join()

        self.filtered_repos = repos_struct.repos_w_students
        self.outputs_log = []

        if len(self.filtered_repos) == 0:
            err = f'{LIGHT_RED}No repos found for specified students.{WHITE}'
            print(err)
            self.outputs_log.append(err)
            return

        print()

        outdir = parent_folder_path[len(self.context.config_manager.config.out_dir) + 1:]
        outdir_str = f'Output directory: {outdir}'
        print(outdir_str)
        self.outputs_log.append(outdir_str)

        for repo_info in self.no_commits_tuples:
            repo_name = repo_info[0]
            repo_new = repo_info[1]
            text = f'    > {LIGHT_RED}Skipping because [{repo_name}] {repo_new} does not have the tag.{WHITE}' if self.clone_via_tag else f'    > {LIGHT_RED}Skipping because [{repo_name}] {repo_new} does not have any commits.{WHITE}'
            print(text)
            self.outputs_log.append(text)

        not_accepted = find_students_not_accepted(self.students, self.filtered_repos, assignment_name, self.no_commits_students, due_tag)
        for student in not_accepted:
            not_accepted_text = f'    > {LIGHT_RED}Skipping because [{student}] {self.students[student]} did not accept the assignment.{WHITE}'
            print(not_accepted_text)
            self.outputs_log.append(not_accepted_text)

        cloned_repos = asyncio.Queue()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.clone_all_repos(self.filtered_repos, parent_folder_path, self.students, assignment_name, self.context.config_manager.config.token, due_tag, cloned_repos))

        if not self.clone_via_tag:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.rollback_all_repos(cloned_repos, due_date, preset.clone_time, flags=flags))
        else:
            del cloned_repos

        stop = time.perf_counter()

        end_report_str = self.print_end_report(len(not_accepted), len(os.listdir(parent_folder_path)), stop - start)
        self.outputs_log.append(end_report_str)
        extract_data_folder(parent_folder_path)

        report = CloneReport(
            assignment_name,
            due_date,
            preset.clone_time,
            datetime.today().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M'),
            due_tag,
            str(students_path),
            tuple(self.outputs_log)
        )

        threading.Thread(target=lambda: self.save_report(report)).start()

        self.filtered_repos.clear()
        self.no_commits_students.clear()
        self.no_commits_tuples.clear()
        del repos_struct

    def print_end_report(self, len_not_accepted: int, cloned_num: int, clone_time: float) -> str:
        '''
        Give end-user somewhat detailed report of what repos were able to be cloned, how many students accepted the assignments, etc.
        '''
        done_str = f'{LIGHT_GREEN}Done.{WHITE}'

        num_accepted = len(self.students) if len_not_accepted == 0 else len(self.students) - len_not_accepted
        accept_str = f'{LIGHT_GREEN}{num_accepted}{WHITE}' if len_not_accepted == 0 else f'{LIGHT_RED}{num_accepted}{WHITE}'
        full_accept_str = f'{LIGHT_GREEN}{accept_str}{LIGHT_GREEN}/{len(self.students)} accepted the assignment.{WHITE}'

        num_no_commits = len(self.no_commits_students & set(self.students.keys())) if len(self.no_commits_students) == 0 else len(self.no_commits_students & set(self.students.keys()))
        commits_str = f'{LIGHT_GREEN}{num_no_commits}{WHITE}' if len(self.no_commits_students) == 0 else f'{LIGHT_RED}{num_no_commits}{WHITE}'
        full_commits_str = f'{LIGHT_RED}{commits_str}{LIGHT_GREEN}/{len(self.students)} had no commits.'

        clone_str = f'{LIGHT_GREEN}{cloned_num}{WHITE}' if cloned_num == len(self.filtered_repos) else f'{LIGHT_RED}{cloned_num}{WHITE}'
        full_clone_str = f'{LIGHT_GREEN}Cloned and Rolled Back {clone_str}{LIGHT_GREEN}/{len(self.filtered_repos)} repos.{WHITE}'

        print()
        print(done_str)
        print(full_accept_str)
        print(full_commits_str)
        print(full_clone_str)

        if self.context.config_manager.config.metrics_api:
            self.context.metrics_client.proxy.repos_cloned(cloned_num)
            self.context.metrics_client.proxy.clone_time(clone_time)
            self.context.metrics_client.proxy.students_accepted(num_accepted)

        full_report_str = f'\n{done_str}\n{full_accept_str}\n{full_commits_str}\n{full_clone_str}'
        return full_report_str

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

    def is_valid_repo(self, repo, assignment_name: str, due_tag: str) -> bool:
        student_github = repo.name.replace(f'{assignment_name}-', '')
        is_student_repo = student_github in self.students
        has_tag = (repo.get_tags().totalCount > 0 and due_tag in [tag.name for tag in repo.get_tags()]) if self.clone_via_tag else True
        if is_student_repo and len(list(repo.get_commits())) - 1 <= 0:
            self.no_commits_tuples.add((repo.name, get_new_repo_name(repo, self.students, assignment_name)))
            self.no_commits_students.add(student_github)
            return False
        elif is_student_repo and not has_tag:
            self.no_commits_tuples.add((repo.name, get_new_repo_name(repo, self.students, assignment_name)))
            self.no_commits_students.add(student_github)
            return False
        return is_student_repo

    def get_repos_specified_students(self, assignment_repos, assignment_name: str, due_tag: str, repos_struct):
        '''
        return list of all repos in an organization matching assignment name prefix and is a student specified in the specified class roster csv
        '''
        repos_struct.repos_w_students = set(filter(lambda repo: self.is_valid_repo(repo, assignment_name, due_tag), assignment_repos))

    async def clone_repo(self, repo, path, filename, token, due_tag, cloned_repos):
        # If no commits, skip repo
        destination_path = f'{path}/{filename}'
        clone_str = f'    > Cloning [{repo.name}] {filename}...'
        print(clone_str)  # tell end user what repo is being cloned and where it is going to
        self.outputs_log.append(clone_str)
        # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user
        clone_url = repo.clone_url.replace('https://', f'https://{token}@')
        cmd = f'git clone --single-branch {clone_url} "{destination_path}"' if not due_tag else f'git clone --branch {due_tag} --single-branch {clone_url} "{destination_path}"'
        await run(cmd)
        local_repo = LocalRepo(destination_path, repo.name, filename, repo)
        await cloned_repos.put(local_repo)
        return True

    async def clone_all_repos(self, repos, path, students, assignment_name, token, due_tag, cloned_repos):
        tasks = []
        for repo in repos:
            task = asyncio.ensure_future(self.clone_repo(repo, path, get_new_repo_name(repo, students, assignment_name), token, due_tag, cloned_repos))
            tasks.append(task)
        await asyncio.gather(*tasks)

    async def rollback_all_repos(self, cloned_repos, date_due, time_due, flags):
        tasks = []
        is_ca = flags[0]
        is_as = flags[1]
        is_ex = flags[2]
        while not cloned_repos.empty():
            repo = await cloned_repos.get()
            student_params = StudentParam('', '', 0, 0, 0)
            for student in self.context.config_manager.config.extra_student_parameters:
                if student.github in repo.old_name():
                    student_params = student
                    break

            hours_adjust = 0
            if is_ca:
                hours_adjust = student_params.class_activity_adj
            elif is_as:
                hours_adjust = student_params.assignment_adj
            elif is_ex:
                hours_adjust = student_params.exam_adj

            if hours_adjust > 0:
                due_datetime = datetime.strptime(f'{date_due} {time_due}', '%Y-%m-%d %H:%M')
                due_datetime += timedelta(hours=hours_adjust)
                due_datetime_strip = due_datetime.strftime('%Y-%m-%d %H:%M').split(' ')
                date_due = due_datetime_strip[0]
                time_due = due_datetime_strip[1]

            commit_hash = await repo.get_commit_hash(date_due, time_due)

            if not commit_hash:
                err_str = f'    > {CYAN}Commit hash failed for [{repo.old_name()}] {repo} retrying...{WHITE}'
                res_str = ''
                print(err_str, end='')
                time.sleep(0.3)
                commit_hash = await repo.get_commit_hash(date_due, time_due)
                if not commit_hash:
                    res_str = f'{LIGHT_RED} failed.{WHITE}'
                    print(res_str)
                    # await log_info('Get Commit Hash Failed', 'Likely accepted assignment after given date/time.', repo)
                    await repo.delete()
                    continue
                else:
                    res_str = f'{LIGHT_GREEN} success.{WHITE}'
                    print(res_str)
                self.outputs_log.append(err_str + res_str)

            task = asyncio.ensure_future(repo.rollback(commit_hash))
            tasks.append(task)
        await asyncio.gather(*tasks)


def extract_data_folder(initial_path, data_folder_name='data'):
    repos = os.listdir(initial_path)
    repo_to_check = repos[len(repos) - 1]
    folders = os.listdir(Path(initial_path) / repo_to_check)
    if data_folder_name in folders:
        shutil.move(f'{str(Path(initial_path) / repo_to_check)}/{data_folder_name}', initial_path)
        print(f'{LIGHT_GREEN}Data folder extracted to the output directory.{WHITE}')


def get_new_repo_name(repo, students: dict, assignment_name: str) -> str:
    '''
    Returns repo name replacing github username sufix with student's real name
    '''
    student_github = repo.name.replace(f'{assignment_name}-', '')
    return f'{assignment_name}-{students[student_github]}'


def attempt_get_assignment():
    '''
    Get assignment name from input. Does not accept empty input.
    '''
    assignment_name = input('Assignment Name: ')  # get assignment name (repo prefix)
    while not assignment_name:  # if input is empty ask again
        assignment_name = input('Please input an assignment name: ')
    return assignment_name


def attempt_get_tag():
    '''
    Get due tag name from input. Does not accept empty input.
    '''
    assignment_name = input('Tag Name: ') # get assignment name (repo prefix)
    while not assignment_name: # if input is empty ask again
        assignment_name = input('Please input an assignment name: ')
    return assignment_name


def get_time():
    '''
    Get assignment due time from input.
    '''
    time_due = input('Time Due (24hr, press `enter` for current): ') # get time assignment was due
    if not time_due: # if time due is blank use current time
        current_time = datetime.now() # get current time
        time_due = current_time.strftime('%H:%M') # format current time into hour:minute 24hr format
        print(f'Using current time: {time_due}') # output what is being used to end user
    return time_due


def get_date():
    '''
    Get assignment due date from input.
    '''
    date_due = input('Date Due (format = yyyy-mm-dd, press `enter` for current): ') # get due date
    if not date_due:  # If due date is blank use current date
        current_date = date.today()  # get current date
        date_due = current_date.strftime('%Y-%m-%d')  # get current date in year-month-day format
        print(f'Using current date: {date_due}')  # output what is being used to end user
    return date_due


def check_date(date_inp: str):
    '''
    Ensure proper date format
    '''
    if not re.match(r'\d{4}-\d{2}-\d{2}', date_inp):
        return False
    return True


def get_repos(assignment_name: str, org_repos) -> Iterable:
    '''
    generator for all repos in an organization matching assignment name prefix
    '''
    for repo in org_repos:
        if repo.name.startswith(assignment_name):
            yield repo


def find_students_not_accepted(students: dict, repos: list, assignment_name: str, no_commits, tag_name: str = '') -> set:
    '''
    Find students who are on the class list but did not have their repos cloned
    '''
    students_keys = set(students.keys())
    accepted = {}
    if tag_name:
        accepted = filter(lambda x: (x.get_tags().totalCount > 0 and (tag_name in x.get_tags()[0].name)), repos)
        accepted = {repo.name.replace(f'{assignment_name}-', '') for repo in accepted}
    else:
        accepted = {repo.name.replace(f'{assignment_name}-', '') for repo in repos}
    return (students_keys ^ accepted) - no_commits


def peek(iterable):
    try:
        first = next(iterable)
    except StopIteration:
        return None
    return itertools.chain([first], iterable)


def verify_assignment_name(assignment_name, org_repos):
    repos = peek(get_repos(assignment_name, org_repos))
    while repos is None or assignment_name == '':
        print(f'{LIGHT_RED}WARNING: There are no repos for that assignment. Enter a valid assignment name.{WHITE}')
        assignment_name = input('Assignment Name: ')
        repos = peek(get_repos(assignment_name, org_repos))
    return assignment_name, repos


def get_students(student_filename: str) -> dict:
    '''
    Reads class roster csv in the format given by github classroom:
    "identifier","github_username","github_id","name"

    and returns a dictionary of students mapping github username to real name
    '''
    students = {}  # student dict
    if Path(student_filename).exists():  # if classroom roster is found
        with open(student_filename) as f_handle:  # use with to auto close file
            csv_reader = csv.reader(f_handle)  # Use csv reader to separate values into a list
            next(csv_reader)  # skip header line
            for student in csv_reader:
                name = re.sub(r'([.]\s?|[,]\s?|\s)', '-', student[0]).rstrip(r'-')
                github = student[1]
                if name and github: # if csv contains student name and github username, map them to each other
                    students[github] = name
    else:
        raise Exception(f'Classroom roster `{student_filename}` does not exist.')
    return students  # return dict mapping names to github username


def onerror(func, path: str, exc_info) -> None:
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


class LocalRepo:
    '''
    Object representing a cloned repo
    '''
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
        '''
        Get commit hash at timestamp and reset local repo to timestamp on the default branch
        '''
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
        '''
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        '''
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
