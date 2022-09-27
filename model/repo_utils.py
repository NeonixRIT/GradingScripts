import asyncio
import csv
import logging
import os
import re
import shutil
import subprocess

from datetime import date, datetime
from typing import Iterable
from github import Github, BadCredentialsException, UnknownObjectException
from github.PaginatedList import PaginatedList
from github.Repository import Repository
from pathlib import Path
'''
Script to clone all or some repositories in a Github Organization based on repo prefix and usernames
@authors  Kamron Cole kjc8084@rit.edu, Trey Pachucki ttp2542@g.rit.edu
'''
CONFIG_PATH = 'tmp/config.txt' # Stores token, org name, save class roster bool, class roster path, output dir
BASE_GITHUB_LINK = 'https://github.com'
MIN_GIT_VERSION = 2.30 # Required 2.30 minimum because of authentication changes
MIN_PYGITHUB_VERSION = 1.55 # Requires 1.55 to allow threading
MAX_THREADS = 200 # Max number of concurrent cloning processes
LOG_FILE_PATH = 'tmp/logs.log' # where the log file goes
LIGHT_GREEN = '\033[1;32m' # Ansi code for light_green
LIGHT_RED = '\033[1;31m' # Ansi code for light_red
WHITE = '\033[0m' # Ansi code for white to reset back to normal text
NO_COMMITS = set() # Keep track of repos w/ 0 commits to exclude when finding students who didnt accept assignment


'''
Possible exceptions caused by github/git
'''
class GithubException(Exception):
    __slots__ = ['message']

    def __init__(self, message) -> None:
        self.message = message


class CloneException(GithubException):
    def __init__(self, message) -> None:
        super().__init__(message)


class RevlistException(GithubException):
    def __init__(self, message) -> None:
        super().__init__(message)


class CommitLogException(GithubException):
    def __init__(self, message) -> None:
        super().__init__(message)


class RollbackException(GithubException):
    def __init__(self, message) -> None:
        super().__init__(message)


class ClientException(GithubException):
    def __init__(self, message) -> None:
        super().__init__(message)


'''
Possible exceptions due to version incompatibility
'''
class CompatibilityException(Exception):
    __slots__ = ['message']

    def __init__(self, message) -> None:
        self.message = message


class InvalidGitVersion(CompatibilityException):
    def __init__(self, message) -> None:
        super().__init__(message)


class GitNotFound(CompatibilityException):
    def __init__(self, message) -> None:
        super().__init__(message)


class InvalidPyGithubVersion(CompatibilityException):
    def __init__(self, message) -> None:
        super().__init__(message)


class PyGithubNotFound(CompatibilityException):
    def __init__(self, message) -> None:
        super().__init__(message)


class PipNotFound(CompatibilityException):
    def __init__(self, message) -> None:
        super().__init__(message)


'''
Possible exceptions due to user error
'''
class UserError(Exception):
    __slots__ = ['message']

    def __init__(self, message) -> None:
        self.message = message


class InvalidAssignmentName(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class InvalidDate(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class InvalidToken(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class InvalidTime(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class InvalidArguments(UserError):
    def __init__(self, message='invalid number of arguments') -> None:
        super().__init__(message)


class ClassroomFileNotFound(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class ConfigFileNotFound(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class OrganizationNotFound(UserError):
    def __init__(self, message) -> None:
        super().__init__(message)


class Version:
    '''
    Object representing a version number used to make comparing and printing script versions easier
    '''
    __slots__ = ['__version_list', '__version_str']


    def __init__(self, version='0.0.0'):
        self.__version_str = version
        self.__version_list = list(version.split('.'))


    def __str__(self):
        return self.__version_str


    def __repr__(self):
        return f'Version[{self.__version_str}, {self.__version_list}]'


    def __lt__(self, other):
        for i in range(len(self.__version_list)):
            version_number = int(self.__version_list[i])
            latest_version_number = int(other.__version_list[i])
            if version_number < latest_version_number:
                return True
            elif version_number > latest_version_number:
                return False
        return False


    def __eq__(self, other):
        if type(other) != Version:
            return False

        return repr(self) == repr(other)


SCRIPT_VERSION = Version('1.1.1')


async def run(cmd: str, cwd=os.getcwd()) -> None:
    '''
    Asyncronously start a subprocess and run a command returning its output
    '''
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    return stdout.decode().strip() if stdout else None, stderr.decode().strip() if stderr else None


async def log_info(msg: str, hint: str, repo, exception: Exception = None) -> None:
    '''
    Helper Function for logging errors to the log file
    '''
    if not Path('./data/logs.log').exists():
        open(LOG_FILE_PATH, 'w').close()
    logging.basicConfig(level=logging.INFO, filename=LOG_FILE_PATH)
    exception_str = exception if exception is not None else ''
    logging.info(
        f'{msg}:\n' + f'  {repr(repo)}\n' + f'  {hint}\n' + f'  {exception_str}\n\n'
    )


async def zip_folder(base_path, sub_dir):
    source_path = f'{base_path}{sub_dir}'
    shutil.make_archive(source_path, 'zip', source_path)
    return f'{source_path}.zip', f'{sub_dir}.zip', True


async def get_files_to_add(input_dir: os.PathLike) -> list[tuple[str, str, bool]]:
    path, folders, files = list(os.walk(input_dir))[0]
    files_to_add = [(f'{path}{file}', file, False) for file in files if file != '.gitkeep']
    folders_to_add = [await zip_folder(path, folder) for folder in folders if not Path(f'{path}{folder}.zip').exists()]
    return files_to_add + folders_to_add


def cleanup_files_to_add(files_to_add: list[tuple[str, str, bool]]):
    for path, _, remove in files_to_add:
        if remove:
            os.remove(path)


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

    def __init__(self, path: str, old_name: str, new_name: str, remote_repo: Repository):
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
            stdout, _ = await run(cmd, self.__path)
            return stdout
        except Exception as e:
            print(f'{LIGHT_RED}[{self}] Get Commit Hash Failed: Likely accepted assignment after given date/time.{WHITE}')
            await log_info('Get Commit Hash Failed', 'Likely accepted assignment after given date/time.', self, e)
            return None


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
        except Exception as e:
            print(f'{LIGHT_RED}[{self}] Rollback Failed: Likely invalid filename at commit `{commit_hash}`.{WHITE}')
            await log_info('Rollback Failed', f'Likely invalid filename at commit `{commit_hash}`.', self, e)
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


def is_windows() -> bool:
    return os.name == 'nt'


def build_init_path(outdir: Path, assignment_name: str, date_inp, time_inp) -> Path:
    date_str = date_inp[4:].replace('-', '_')
    time_str = time_inp.replace(':', '_')
    init_path = outdir / f'{assignment_name}{date_str}_{time_str}'

    index = 1
    if init_path.exists():
        new_path = Path(f'{init_path}_iter_{index}')
        while new_path.exists():
            index += 1
            new_path = Path(f'{init_path}_iter_{index}')
        return new_path
    return init_path


def get_repos(assignment_name: str, org_repos: PaginatedList) -> Iterable:
    '''
    generator for all repos in an organization matching assignment name prefix
    '''
    for repo in org_repos:
        if repo.name.startswith(assignment_name):
            yield repo


def is_valid_repo(repo: Repository, students: dict, assignment_name: str) -> bool:
    is_student_repo = repo.name.replace(f'{assignment_name}-', '') in students
    if is_student_repo and len(list(repo.get_commits())) - 1 <= 0:
        print(f'{LIGHT_RED}[{repo.name}] No commits.{WHITE}')
        # logging.warning(f'Skipping `{repo.name}` because is has 0 commits.')
        NO_COMMITS.add(repo.name.replace(f'{assignment_name}-', ''))
        return False
    return is_student_repo


def get_repos_specified_students(assignment_repos: Iterable, students: dict, assignment_name: str) -> set:
    '''
    return list of all repos in an organization matching assignment name prefix and is a student specified in the specified class roster csv
    '''
    return set(filter(lambda repo: is_valid_repo(repo, students, assignment_name), assignment_repos))


def get_students(student_filename: str) -> dict:
    '''
    Reads class roster csv in the format given by github classroom:
    "identifier","github_username","github_id","name"

    and returns a dictionary of students mapping github username to real name
    '''
    students = {} # student dict
    if Path(student_filename).exists(): # if classroom roster is found
        with open(student_filename) as f_handle: # use with to auto close file
            csv_reader = csv.reader(f_handle) # Use csv reader to separate values into a list
            next(csv_reader) # skip header line
            for student in csv_reader:
                name = re.sub(r'([.]\s?|[,]\s?|\s)', '-', student[0]).rstrip(r'-')
                github = student[1]
                if name and github: # if csv contains student name and github username, map them to each other
                    students[github] = name
    else:
        raise ClassroomFileNotFound(f'Classroom roster `{student_filename}` does not exist.')
    return students # return dict mapping names to github username


def get_new_repo_name(repo: Repository, students: dict, assignment_name: str) -> str:
    '''
    Returns repo name replacing github username sufix with student's real name
    '''
    student_github = repo.name.replace(f'{assignment_name}-', '')
    return f'{assignment_name}-{students[student_github]}'


def save_config(token: str, organization: str, student_filename: str, output_dir: Path):
    '''
    Save parameters into config file to be read on future runs
    '''
    with open(CONFIG_PATH, 'w') as config:
        config.write(f'Token: {token}')
        config.write('\n')
        config.write(f'Organization: {organization}')
        config.write('\n')
        config.write(f'Save Classroom Roster: {str(True)}')
        config.write('\n')
        config.write(f'Classroom Roster Path: {student_filename}')
        config.write('\n')
        config.write(f'Output Directory: {str(output_dir)}')


def read_config_raw() -> tuple:
    '''
    Reads config containing token, organization, whether to use class list, and path of class list.
    Return values as tuple
    '''
    token = ''
    organization = ''
    student_filename = ''
    output_dir = ''
    if Path(CONFIG_PATH).exists():
        with open(CONFIG_PATH, 'r') as config:
            token = config.readline().strip().split(': ')[1]
            organization = config.readline().strip().split(': ')[1]
            _ = config.readline().strip().split(': ')[1]
            student_filename = config.readline().strip().split(': ')[1]
            output_dir = Path(config.readline().strip().split(': ')[1])
    else:
        raise ConfigFileNotFound(f'`{CONFIG_PATH}` does not exist')
    return (token, organization, student_filename, output_dir)


def read_config() -> tuple:
    '''
    Checks whether config already exists, if not make default config
    '''
    if Path(CONFIG_PATH).exists(): # If config already exists
        token, organization, student_filename, output_dir = read_config_raw() # get variables
    else:
        make_default_config()
        token, organization, student_filename, output_dir = read_config_raw() # Update return variables
    return (token, organization, student_filename, output_dir)


def make_default_config() -> None:
    '''
    Creates a default config file getting access token, org, class roster, etc, from user input
    '''
    student_filename = ''
    token = input('Github Authentication Token: ')
    organization = input('Organization Name: ')
    student_filename = input('Enter filename of csv file containing username and name of students: ')
    output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))
    if not output_dir:
        output_dir = Path.cwd()
    while not Path.is_dir(output_dir):
        print(f'Directory `{output_dir}` not found.')
        output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))
    save_config(token, organization, student_filename, output_dir)


def is_update_available(latest_release) -> bool:
    try:
        latest_version = Version(latest_release.tag_name)
        return SCRIPT_VERSION < latest_version
    except Exception:
        return False


def print_release_changes_since_update(releases) -> None:
    print(f'{LIGHT_GREEN}An upadate is available. {SCRIPT_VERSION} -> {releases[0].tag_name}{WHITE}')
    for release in list(releases)[::-1]:
        release_version = Version(release.tag_name)
        if release_version > SCRIPT_VERSION:
            print(f'{LIGHT_GREEN}Version: {release_version}\nDescription:\n{release.body}\n{WHITE}')


def check_and_print_updates(token: str):
    client = Github(token.strip())
    repo = client.get_repo('NeonixRIT/GradingScripts')
    releases = repo.get_releases()
    latest = releases[0]
    if is_update_available(latest):
        print_release_changes_since_update(releases)


def check_git_version():
    '''
    Check that git version is at or above min requirements for script
    '''
    try:
        git_version = subprocess.check_output(['git', '--version'], stderr=subprocess.PIPE).decode().strip()[12:16]
        if float(git_version) < MIN_GIT_VERSION:
            raise InvalidGitVersion(f'Your version of git is not compatible with this script. Use version {MIN_GIT_VERSION}+.')
    except FileNotFoundError:
        raise GitNotFound('git not installed on the path.')


def pyversion_short(subprocess: subprocess.Popen):
    '''
    Error logic for alternate pip commands when trying to find pyversion.
    '''
    with subprocess:
        for line in iter(subprocess.stdout.readline, b''): # b'\n'-separated lines
            line = line.decode().lower()
            if 'version:' in line:
                return float(line.split(': ')[1][0:4])
            elif 'not found:' in line:
                raise PyGithubNotFound()
            else:
                return 99.99


def try_alt_pygithub_check():
    '''
    Attempt alternate commands to find proper pygithub version
    '''
    try:
        if is_windows():
            check_pygithub_version_process = subprocess.Popen(['python', '-m', 'pip', 'show', 'pygithub'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if pyversion_short(check_pygithub_version_process) < MIN_PYGITHUB_VERSION:
                raise InvalidPyGithubVersion(f'Incompatible PyGithub version. Use version {MIN_PYGITHUB_VERSION}+. Use `pip install PyGithub --upgrade` to update')
        else:
            check_pygithub_version_process = subprocess.Popen(['python3', '-m', 'pip', 'show', 'pygithub'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if pyversion_short(check_pygithub_version_process) < MIN_PYGITHUB_VERSION:
                raise InvalidPyGithubVersion(f'Incompatible PyGithub version. Use version {MIN_PYGITHUB_VERSION}+. Use `pip install PyGithub --upgrade` to update')
    except FileNotFoundError:
        raise PipNotFound('pip not found.')
    except Exception as e:
        logging.warning(f"Error occured while handling the pip process: {e}")


def check_pygithub_version():
    '''
    Check that PyGithub version is at or above min requirements for script
    '''
    try:
        check_pygithub_version_process = subprocess.Popen(['pip', 'show', 'pygithub'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if pyversion_short(check_pygithub_version_process) < MIN_PYGITHUB_VERSION:
            logging.warning('Incompatible PyGithub version.')
            raise InvalidPyGithubVersion(f'Incompatible PyGithub version. Use version {MIN_PYGITHUB_VERSION}+. Use `pip install PyGithub --upgrade` to update')
    except FileNotFoundError:
        logging.warning('pip not installed on the path, trying alternative...')
        try_alt_pygithub_check()
    except PyGithubNotFound:
        logging.warning('PyGithub not found in default pip path, trying alternative...')
        try:
            try_alt_pygithub_check()
        except Exception:
            raise PyGithubNotFound('PyGithub not found. Please install the latest version using pip. Make sure it is for the version of python you are trying to run the script from.')
    except Exception as e:
        logging.warning(f"Error occured while handling the pip process: {e}")


def check_date(date_inp: str):
    '''
    Ensure proper date format
    '''
    if not re.match(r'\d{4}-\d{2}-\d{2}', date_inp):
        return False
    return True


def check_time(time_inp: str):
    '''
    Ensure proper time format
    '''
    if not re.match(r'\d{2}:\d{2}', time_inp):
        return False
    return True


def check_assignment_name(repos: str):
    '''
    Ensure there are repos for the assignment
    '''
    if not repos:
        raise InvalidAssignmentName('Assignment doesn\'t exist.')


def attempt_get_assignment():
    '''
    Get assignment name from input. Does not accept empty input.
    '''
    assignment_name = input('Assignment Name: ') # get assignment name (repo prefix)
    while not assignment_name: # if input is empty ask again
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
    if not date_due: # If due date is blank use current date
        current_date = date.today() # get current date
        date_due = current_date.strftime('%Y-%m-%d') # get current date in year-month-day format
        print(f'Using current date: {date_due}') # output what is being used to end user
    return date_due


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


def update_organization(token: str, student_filename: str, output_dir: Path) -> tuple:
    '''
    Update organization name in config.txt file. Returns updated config.
    '''
    new_organization = input('New Github Organization name: ')
    save_config(token, new_organization, student_filename, output_dir)
    return (token, new_organization, student_filename, output_dir)


def update_token(organization: str, student_filename: str, output_dir: Path) -> tuple:
    '''
    Update token string in config.txt file. Return updated config.
    '''
    new_token = input('New Github O-Auth token: ')
    save_config(new_token, organization, student_filename, output_dir)
    return (new_token, organization, student_filename, output_dir)


def prompt_invalid_tok_org(exception: Exception, token: str, organization: str, student_filename: str, output_dir: Path) -> tuple:
    '''
    Prompt user and attempt to fix invalid tokens/organizations in config.txt
    '''
    ex_type = type(exception)
    prompt_str = 'O-Auth token' if ex_type is BadCredentialsException else 'Organization name'

    logging.warning(f'Invalid {prompt_str}.')
    print(f'{LIGHT_RED}Invalid {prompt_str}.{WHITE}')
    response = input(f'Would you like to update your {prompt_str} in config.txt? (Y/N): ')
    if response.lower() == 'y' or response.lower() == 'yes':
        if ex_type == BadCredentialsException:
            return update_token(organization, student_filename, output_dir)
        elif ex_type == UnknownObjectException:
            return update_organization(token, student_filename, output_dir)
    else:
        exit()


def attempt_make_client(token: str, organization: str, student_filename: str, output_dir: Path):
    '''
    Attempts to make and return github client for the organization to get repo information with.
    Attempts to fix invalid organization/token issues and gives repeated attempts for other issues.
    '''
    attempts = 0
    while attempts < 5:
        try:
            return Github(token.strip(), pool_size=MAX_THREADS).get_organization(organization.strip())
        except (BadCredentialsException, UnknownObjectException) as e:
            token, organization, student_filename, output_dir = prompt_invalid_tok_org(e, token, organization, student_filename, output_dir)
        except Exception as e:
            logging.warning(e)
        attempts += 1
    raise ClientException('Unable to Create Github Client.')


async def clone_repo(repo, path, filename, token, due_tag, cloned_repos):
    # If no commits, skip repo
    destination_path = f'{path}/{filename}'
    print(f'    > Cloning [{repo.name}] {filename}...') # tell end user what repo is being cloned and where it is going to
    # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user
    clone_url = repo.clone_url.replace('https://', f'https://{token}@')
    cmd = f'git clone --single-branch {clone_url} "{destination_path}"' if not due_tag else f'git clone --branch {due_tag} --single-branch {clone_url} "{destination_path}"'
    await run(cmd)
    local_repo = LocalRepo(destination_path, repo.name, filename, repo)
    await cloned_repos.put(local_repo)
    return True


async def clone_all_repos(repos, path, students, assignment_name, token, due_tag, cloned_repos):
    tasks = []
    for repo in repos:
        task = asyncio.ensure_future(clone_repo(repo, path, get_new_repo_name(repo, students, assignment_name), token, due_tag, cloned_repos))
        tasks.append(task)
    await asyncio.gather(*tasks)


async def rollback_all_repos(cloned_repos, date_due, time_due):
    tasks = []
    while not cloned_repos.empty():
        repo = await cloned_repos.get()
        commit_hash = await repo.get_commit_hash(date_due, time_due)

        if not commit_hash:
            print(f'    > {LIGHT_RED}Get Commit Hash Failed: [{repo.old_name()}] {repo} likely accepted assignment after given date/time.{WHITE}')
            await log_info('Get Commit Hash Failed', 'Likely accepted assignment after given date/time.', repo)
            await repo.delete()
            continue

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


def print_end_report(students: dict, repos: list, len_not_accepted: int, cloned_num: int, no_commits) -> None:
    '''
    Give end-user somewhat detailed report of what repos were able to be cloned, how many students accepted the assignments, etc.
    '''
    print()
    print(f'{LIGHT_GREEN}Done.{WHITE}')

    accept_str = f'{LIGHT_GREEN}{len(students)}{WHITE}' if len_not_accepted == 0 else f'{LIGHT_RED}{len(students) - len_not_accepted}{WHITE}'
    print(f'{LIGHT_GREEN}{accept_str}{LIGHT_GREEN}/{len(students)} accepted the assignment.{WHITE}')

    commits_str = f'{LIGHT_GREEN}{len(no_commits & set(students.keys()))}{WHITE}' if len(no_commits) == 0 else f'{LIGHT_RED}{len(no_commits & set(students.keys()))}{WHITE}'
    print(f'{LIGHT_RED}{commits_str}{LIGHT_GREEN}/{len(students)} had no commits.')

    clone_str = f'{LIGHT_GREEN}{cloned_num}{WHITE}' if cloned_num == len(repos) else f'{LIGHT_RED}{cloned_num}{WHITE}'
    print(f'{LIGHT_GREEN}Cloned and Rolled Back {clone_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')


async def add_to_all_repos(input_path: os.PathLike, commit_message: str, cloned_repos: asyncio.Queue[LocalRepo]):
    tasks = []
    files_to_add = await get_files_to_add(input_path)
    while not cloned_repos.empty():
        repo = await cloned_repos.get()
        task = asyncio.ensure_future(repo.add(files_to_add, commit_message))
        tasks.append(task)
    await asyncio.gather(*tasks)


async def clone_repos_routine():
    pass


async def rollback_repos_routine():
    pass


async def add_to_repos_routine():
    pass


def main():
    try:
        # Enable color in cmd
        if is_windows():
            os.system('color')
        # Create log file
        if not Path(LOG_FILE_PATH).exists():
            open(LOG_FILE_PATH, 'w').close()
        logging.basicConfig(level=logging.INFO, filename=LOG_FILE_PATH)

        # Check local git version is compatible with script
        check_git_version()
        # Check local PyGithub module version is compatible with script
        check_pygithub_version()
        # Read config file, if doesn't exist make one using user input.
        token, organization, student_filename, output_dir = read_config()
        # Check if update is available for the script and print the description
        check_and_print_updates(token)

        # Create Organization to access repos, raise errors if invalid token/org
        git_org_client = attempt_make_client(token, organization, student_filename, output_dir)

        org_repos = git_org_client.get_repos()

        # Variables used to get proper repos
        assignment_name = attempt_get_assignment()
        date_due = get_date()
        time_due = get_time()

        print() # new line for formatting reasons

        students = dict() # student dict variable do be used im main scope
        repos = get_repos(assignment_name, org_repos)
        students = get_students(student_filename) # fill student dict
        repos = get_repos_specified_students(repos, students, assignment_name)

        check_time(time_due)
        check_date(date_due)
        check_assignment_name(repos)
        # Sets path to output directory inside assignment folder where repos will be cloned.
        # Makes parent folder for whole assignment.
        initial_path = build_init_path(output_dir, assignment_name, date_due, time_due)
        os.mkdir(initial_path)

        print()

        # Print and log students that have not accepted assignment
        not_accepted = set()
        not_accepted = find_students_not_accepted(students, repos, assignment_name)
        for student in not_accepted:
            print(f'{LIGHT_RED}`{students[student]}` ({student}) did not accept the assignment.{WHITE}')
            logging.info(f'{students[student]}` ({student}) did not accept the assignment `{assignment_name}` by the due date/time.')

        if len(not_accepted) != 0:
            print()

        cloned_repos = asyncio.Queue()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(clone_all_repos(repos, initial_path, students, assignment_name, token, cloned_repos))

        print()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(rollback_all_repos(cloned_repos, date_due, time_due))

        print_end_report(students, repos, len(not_accepted), len(os.listdir(initial_path)))
        extract_data_folder(initial_path)
    except Exception as e:
        logging.warning(f'{type(e)}: {e}')
        print()
        try:
            print(f'{LIGHT_RED}{e.message}{WHITE}')
        except Exception:
            print(f'{LIGHT_RED}{type(e)}: {e}{WHITE}')


if __name__ == '__main__':
    main()
