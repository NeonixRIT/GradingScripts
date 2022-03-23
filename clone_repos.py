import csv
import logging
import os
import re
import shutil
import subprocess
import threading

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
AVERAGE_LINES_FILENAME = 'avgLinesInserted.txt'
CONFIG_PATH = 'tmp/config.txt' # Stores token, org name, save class roster bool, class roster path, output dir
BASE_GITHUB_LINK = 'https://github.com'
SCRIPT_VERSION = '1.0.3'
MIN_GIT_VERSION = 2.30 # Required 2.30 minimum because of authentication changes
MIN_PYGITHUB_VERSION = 1.55 # Requires 1.55 to allow threading
MAX_THREADS = 200 # Max number of concurrent cloning processes
LOG_FILE_PATH = 'tmp/logs.log' # where the log file goes
LIGHT_GREEN = '\033[1;32m' # Ansi code for light_green
LIGHT_RED = '\033[1;31m' # Ansi code for light_red
WHITE = '\033[0m' # Ansi code for white to reset back to normal text
AVG_INSERTIONS_DICT = dict() # Global dict that threads map repos to average lines of code per commit


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


class AtomicCounter:
    '''
    Simple Thread safe integer
    '''
    __slots__ = ['value', '_lock']


    def __init__(self, initial=0):
        """Initialize a new atomic counter to given initial value (default 0)."""
        self.value = initial
        self._lock = threading.Lock()


    def increment(self, num=1):
        """Atomically increment the counter by num (default 1) and return the
        new value.
        """
        with self._lock:
            self.value += num
            return self.value


class RepoHandler(threading.Thread):
    '''
    A Thread that clones a repo, resets it to specific time, and gets average number of lines per commit

    Each thread only clones one repo.
    '''
    __slots___ = ['__repo', '__assignment_name', '__date_due', '__time_due', '__students', '__initial_path', '__repo_path', '__token', '__new_repo_name', '__is_cloned']


    def __init__(self, repo: Repository, assignment_name: str, date_due: str, time_due: str, students: dict, initial_path: Path, token: str):
        self.__repo = repo # PyGithub repo object
        self.__assignment_name = assignment_name # Repo name prefix
        self.__date_due = date_due
        self.__time_due = time_due
        self.__students = students
        self.__initial_path = initial_path
        self.__new_repo_name = get_new_repo_name(self.__repo, self.__students, self.__assignment_name)
        self.__repo_path = self.__initial_path / self.__new_repo_name # replace repo name when cloning to have student's real name
        self.__token = token
        self.__is_cloned = False
        super().__init__()


    def run(self):
        '''
        Clones given repo and renames destination to student real name if class roster is provided.
        '''
        try:
            # If no commits, skip repo
            try:
                student_commits = len(list(self.__repo.get_commits())) - 1
                if student_commits == 0:
                    raise CloneException()
            except Exception:
                print(f'{LIGHT_RED}Skipping `{self.__repo.name}` because it has 0 commits.{WHITE}')
                logging.warning(f'Skipping repo `{self.__repo.name}` because it has 0 commits.')
                return

            self.clone_repo() # clones repo
            cloned_counter.increment()
            commit_hash = self.get_commit_hash() # get commit hash at due date
            self.rollback_repo(commit_hash) # rollback repo to commit hash
            rollback_counter.increment()
            self.get_repo_stats() # get average lines per commit
        except GithubException as ge:
            print(f'{LIGHT_RED}Skipping repo `{self.__repo.name}` because: {ge.message}{WHITE}')
            logging.warning(f'{self.__repo.name}: {ge}')
            try:
                if self.__is_cloned:
                    delete_repo_on_error(self.__repo_path)
            except Exception:
                print(f'{LIGHT_RED}Failed to delete skipped repo.{WHITE}')


    def run_raise(self):
        '''
        Sepatate run method used for unit testing
        '''
        try:
            # If no commits, skip repo
            try:
                student_commits = len(list(self.__repo.get_commits())) - 1
                if student_commits == 0:
                    raise CloneException()
            except Exception:
                print(f'{LIGHT_RED}Skipping `{self.__repo.name}` because it has 0 commits.{WHITE}')
                logging.warning(f'Skipping repo `{self.__repo.name}` because it has 0 commits.')
                return

            self.clone_repo() # clones repo
            cloned_counter.increment()
            commit_hash = self.get_commit_hash() # get commit hash at due date
            self.rollback_repo(commit_hash) # rollback repo to commit hash
            rollback_counter.increment()
            self.get_repo_stats() # get average lines per commit
        except GithubException as ge:
            print(f'{LIGHT_RED}Skipping repo `{self.__repo.name}` because: {ge.message}{WHITE}')
            logging.warning(f'{self.__repo.name}: {ge}')
            if self.__is_cloned:
                delete_repo_on_error(self.__repo_path)
            raise ge


    def clone_repo(self):
        '''
        Clones a repo into the assignment folder.

        Due to some weird authentication issues. Git clone might need to have the github link with the token passed e.g.
        https://www.<token>@github.com/<organization>/<Repository.name>
        '''
        print(f'Cloning {self.__repo.name} into {self.__repo_path}...') # tell end user what repo is being cloned and where it is going to
        # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user

        clone_url = self.__repo.clone_url.replace('https://', f'https://{self.__token}@')
        clone_process = subprocess.Popen(['git', 'clone', clone_url, '--single-branch', f'{str(self.__repo_path)}'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT) # git clone to output file, Hides output from console
        try:
            self.log_errors_given_subprocess(clone_process) # reads output line by line and checks for errors that occured during cloning
        except GithubException:
            logging.warning('Clone failed (likely due to invalid filename).') # log error to log file
            raise CloneException('Clone failed (likely due to invalid filename).')
        self.__is_cloned = True


    def get_commit_hash(self) -> str:
        '''
        Get commit hash at timestamp and reset local repo to timestamp on the default branch
        '''
        # run process on system that executes 'git rev-list' command. stdout is redirected so it doesn't output to end user
        rev_list_process = subprocess.Popen(['git', 'rev-list', '-n', '1', '--date=local', f'--before="{self.__date_due.strip()} {self.__time_due.strip()}"', f'origin/{self.__repo.default_branch}'], cwd=self.__repo_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with rev_list_process: # Read rev list output line by line to search for error or commit hash
            for line in iter(rev_list_process.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode()
                try:
                    self.log_errors_given_line(line) # if command returned error raise exception
                except GithubException:
                    logging.warning('Error occured while retrieving commit hash at time/date (likely due to student accepting assignment after given date/time).')
                    raise RevlistException('Error occured while retrieving commit hash at time/date (likely due to student accepting assignment after given date/time).')
                return line.strip() # else returns commit hash of repo at timestamp


    def rollback_repo(self, commit_hash):
        '''
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        '''
        if not commit_hash:
            raise RollbackException('Invalid commit hash (likely due to student accepting assignment after given date/time).')
        # run process on system that executes 'git reset' command. stdout is redirected so it doesn't output to end user
        # git reset is similar to checkout but doesn't care about detached heads and is more forceful
        checkout_process = subprocess.Popen(['git', 'reset', '--hard', commit_hash], cwd=self.__repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            self.log_errors_given_subprocess(checkout_process)
        except GithubException:
            logging.warning(f'Rollback failed for `{self.__repo.name}` (likely due to invalid filename at specified commit).')
            raise RollbackException(f'Rollback failed for `{self.__repo.name}` (likely due to invalid filename at specified commit).')


    def get_repo_stats(self):
        '''
        Get commit history stats and find average number of insertions per commit
        '''
        try:
            # run process on system that executes 'git log' command. stdout is redirected so it doesn't output to end user
            # output is something like this format:
            # <short commit hash> <commit message>
            #  <x> file(s) changed, <x> insertions(+)
            log_process = subprocess.Popen(['git', 'log', '--oneline', '--shortstat'], cwd=self.__repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # Loop through response line by line
            repo_stats = [] # list to store each commits insertion number
            total_insertions = 0
            with log_process:
                for line in iter(log_process.stdout.readline, b''): # b'\n'-separated lines
                    line = line.decode()
                    self.log_errors_given_line(line)
                    if (re.match(r"^\s\d+\sfile.*changed,\s\d+\sinsertion.*[(+)].*", line)): # if line has insertion number in it
                        # Replaces all non digits in a string with nothing and appends the commit's stats to repo_stats list
                        # [0] = files changed
                        # [1] = insertions
                        # [2] = deletions (if any, might not be an index)
                        stat_entry = [re.sub(r'\D', '', value) for value in line.strip().split(', ')]
                        repo_stats.append(stat_entry)
                        total_insertions += int(stat_entry[1])

            total_commits = len(repo_stats) # each index in repo_stats should be a commit

            # Calc avg and place in global dictionary using maped repo name if student roster is provided or normal repo name
            average_insertions = round(total_insertions / total_commits, 2)
            AVG_INSERTIONS_DICT[self.__new_repo_name] = average_insertions
        except Exception:
            logging.warning(f'Failed to find average insertions for {self.__repo.name}')
            raise CommitLogException(f'Failed to find average insertions for {self.__repo.name}')


    def log_errors_given_line(self, line: str):
        '''
        Given 1 line of git command output, check if error.
        If so, log it and raise exception
        '''
        if re.match(r'^error:|^warning:|^fatal:', line): # if git command threw error (usually wrong branch name)
            logging.warning('Subprocess: %r', line) # Log error to log file
            raise GithubException('An error has occured with git.') # Raise exception to the thread


    def log_errors_given_subprocess(self, subprocess: subprocess.Popen):
        '''
        Reads full git command output of a subprocess and raises exception & logs if error is found
        '''
        with subprocess:
            for line in iter(subprocess.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode() # line is read in bytes. Decode to str
                self.log_errors_given_line(line)


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


def get_repos_specified_students(assignment_repos: Iterable, students: dict, assignment_name: str) -> set:
    '''
    return list of all repos in an organization matching assignment name prefix and is a student specified in the specified class roster csv
    '''
    return set(filter(lambda repo: repo.name.replace(f'{assignment_name}-', '') in students, assignment_repos))


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


def make_default_config():
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


def check_update_available(token: str) -> bool:
    try:
        client = Github(token.strip())
        repo = client.get_repo('NeonixRIT/GradingScripts')
        releases = repo.get_releases()
        latest = releases[0]
        latest_version = latest.tag_name

        version_split = SCRIPT_VERSION.split('.')
        latest_version_split = latest_version.split('.')

        for i in range(len(version_split)):
            version_number = int(version_split[i])
            latest_version_number = int(latest_version_split[i])
            if version_number < latest_version_number:
                update_print_and_prompt(latest)
                return True
            elif version_number > latest_version_number:
                return False
        return False
    except Exception:
        return False


def update_print_and_prompt(latest_release):
    print(f'{LIGHT_GREEN}An upadate is available. {SCRIPT_VERSION} -> {latest_release.tag_name}\nDescription:\n{latest_release.body}\n{WHITE}')


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
            if 'not found:' in line:
                raise PyGithubNotFound()


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


def write_avg_insersions_file(initial_path: Path, assignment_name: str):
    '''
    Loop through average insertions dict created by CloneRepoThreads and write to file in assignment dir
    '''
    num_of_lines = 0
    local_dict = AVG_INSERTIONS_DICT
    local_dict = dict(sorted(local_dict.items(), key=lambda item: item[0]))
    with open(initial_path / AVERAGE_LINES_FILENAME, 'w') as avgLinesFile:
        avgLinesFile.write(f'{assignment_name}\n\n')
        for repo_name in local_dict:
            avgLinesFile.write(f'{repo_name.replace(f"{assignment_name}-", "").replace("-", ", ")}\n    Average Insertions: {local_dict[repo_name]}\n\n')
            num_of_lines += 1
    return num_of_lines


def check_date(date_inp: str):
    '''
    Ensure proper date format
    '''
    if not re.match(r'\d{4}-\d{2}-\d{2}', date_inp):
        raise InvalidDate('Invalid date format.')


def check_time(time_inp: str):
    '''
    Ensure proper time format
    '''
    if not re.match(r'\d{2}:\d{2}', time_inp):
        raise InvalidTime('Invalid time format.')


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


def get_time():
    '''
    Get assignment due time from input.
    '''
    time_due = input('Time Due (24hr, press `enter` for current): ') # get time assignment was due
    if not time_due: # if time due is blank use current time
        current_time = datetime.now() # get current time
        time_due = current_time.strftime('%H:%M') # format current time into hour:minute 24hr format
        print(f'Using current date: {time_due}') # output what is being used to end user
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


def find_students_not_accepted(students: dict, repos: list, assignment_name: str) -> set:
    '''
    Find students who are on the class list but did not have their repos cloned
    '''
    students_keys = set(students.keys())
    accepted = {repo.name.replace(f'{assignment_name}-', '') for repo in repos}
    return students_keys ^ accepted


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


def print_end_report(students: dict, repos: list, len_not_accepted, cloned_num: int, rollback_num: int, lines_written: int):
    '''
    Give end-user somewhat detailed report of what repos were able to be cloned, how many students accepted the assignments, etc.
    '''
    print()
    print(f'{LIGHT_GREEN}Done.{WHITE}')

    accept_str = f'{LIGHT_GREEN}{len(students)}{WHITE}' if len_not_accepted == 0 else f'{LIGHT_RED}{len(students) - len_not_accepted}{WHITE}'
    print(f'{LIGHT_GREEN}{accept_str}{LIGHT_GREEN}/{len(students)} accepted the assignment.{WHITE}')

    clone_str = f'{LIGHT_GREEN}{cloned_num}{WHITE}' if cloned_num == len(repos) else f'{LIGHT_RED}{cloned_num}{WHITE}'
    print(f'{LIGHT_GREEN}Cloned {clone_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')

    rollback_str = f'{LIGHT_GREEN}{rollback_num}{WHITE}' if rollback_num == len(repos) else f'{LIGHT_RED}{rollback_num}{WHITE}'
    print(f'{LIGHT_GREEN}Rolled Back {rollback_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')

    lines_str = f'{LIGHT_GREEN}{lines_written}{WHITE}' if lines_written == len(repos) else f'{LIGHT_RED}{lines_written}{WHITE}'
    print(f'{LIGHT_GREEN}Found average lines per commit for {lines_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')


def log_timing_report(timings: dict, assignment_name: str):
    logging.info('*** Start Timing report ***')
    logging.info('    Assignment:'.ljust(34) + assignment_name)
    for key in timings.keys():
        prefix = f'    {key}:'.ljust(34)
        logging.info(f'{prefix}{str(round(timings[key], 5))}')
    logging.info('*** End Timing report ***')


def onerror(func, path: str, exc_info) -> None:
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def delete_repo_on_error(path: str, onerror=onerror) -> None:
    shutil.rmtree(path, onerror=onerror)


def extract_data_folder(initial_path, data_folder_name='data'):
    repos = os.listdir(initial_path)
    repo_to_check = repos[len(repos) - 1]
    folders = os.listdir(Path(initial_path) / repo_to_check)
    if data_folder_name in folders:
        shutil.move(f'{str(Path(initial_path) / repo_to_check)}/{data_folder_name}', initial_path)


rollback_counter = AtomicCounter()
cloned_counter = AtomicCounter()


def main():
    '''
    Main function
    '''

    # Enable color in cmd
    if is_windows():
        os.system('color')
    # Create log file
    logging.basicConfig(level=logging.INFO, filename=LOG_FILE_PATH)

    # Try catch catches errors and sends them to the log file instead of outputting to console
    try:
        # Check local git version is compatible with script
        check_git_version()
        # Check local PyGithub module version is compatible with script
        check_pygithub_version()
        # Read config file, if doesn't exist make one using user input.
        token, organization, student_filename, output_dir = read_config()
        # Check if update is available for the script and print the description
        check_update_available(token)

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

        # Print and log students that have not accepted assignment
        not_accepted = set()
        not_accepted = find_students_not_accepted(students, repos, assignment_name)
        for student in not_accepted:
            print(f'{LIGHT_RED}`{students[student]}` ({student}) did not accept the assignment.{WHITE}')
            logging.info(f'{students[student]}` ({student}) did not accept the assignment `{assignment_name}` by the due date/time.')

        if len(not_accepted) != 0:
            print()

        threads = []
        # goes through list of repos and clones them into the assignment's parent folder
        for repo in repos:
            # Create thread to handle repos and add to thread list
            # Each thread clones a repo, sets it back to due date/time, and gets avg lines per commit
            thread = RepoHandler(repo, assignment_name, date_due, time_due, students, initial_path, token)
            threads += [thread]

        # Run all clone threads
        for thread in threads:
            thread.start()

        # Make main thread wait for all repos to be cloned, set back to due date/time, and avg lines per commit to be found
        for thread in threads:
            thread.join()

        num_of_lines = write_avg_insersions_file(initial_path, assignment_name)
        print_end_report(students, repos, len(not_accepted), cloned_counter.value, rollback_counter.value, num_of_lines)
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
