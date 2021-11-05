import csv
import logging
import os
import re
import shutil
import subprocess
import _thread

from datetime import date, datetime
from github import Github
from github.Organization import Organization
from github.Repository import Repository
from pathlib import Path
from threading import Thread
'''
Script to clone all or some repositories in a Github Organization based on repo prefix and usernames
@authors  Kamron Cole kjc8084@rit.edu, Trey Pachucki ttp2542@g.rit.edu
'''
AVERAGE_LINES_FILENAME = 'avgLinesInserted.txt'
CONFIG_PATH = 'tmp/config.txt' # Stores token, org name, save class roster bool, class roster path, output dir
BASE_GITHUB_LINK = 'https://github.com'
MIN_GIT_VERSION = 2.30 # Required 2.30 minimum because of authentication changes
MIN_PYGITHUB_VERSION = 1.55 # Requires 1.55 to allow threading
MAX_THREADS = 200 # Max number of concurrent cloning processes
LOG_FILE_PATH = 'tmp/logs.log' # where the log file goes
LIGHT_GREEN = '\033[1;32m' # Ansi code for light_green
LIGHT_RED = '\033[1;31m' # Ansi code for light_red
WHITE = '\033[0m' # Ansi code for white to reset back to normal text
AVG_INSERTIONS_DICT = dict() # Global dict that threads map repos to average lines of code per commit


class RepoHandler(Thread):
    '''
    A Thread that clones a repo, resets it to specific time, and gets average number of lines per commit

    Each thread only clones one repo.
    '''
    __slots___ = ['__repo', '__assignment_name', '__date_due', '__time_due', '__students', '__student_filename', '__initial_path', '__repo_path']


    def __init__(self, repo: Repository, assignment_name: str, date_due: str, time_due: str, students: dict, student_filename: str, initial_path: Path):
        self.__repo = repo # PyGithub repo object
        self.__assignment_name = assignment_name # Repo name prefix
        self.__date_due = date_due 
        self.__time_due = time_due
        self.__students = students #
        self.__student_filename = student_filename
        self.__initial_path = initial_path
        if self.__student_filename: # If a classroom roster is used, replace github name with real name
            self.__repo_path = self.__initial_path / get_new_repo_name(self.__repo, self.__students, self.__assignment_name) # replace repo name when cloning to have student's real name
        else:
            self.__repo_path = self.__initial_path / self.__repo.name
        super().__init__()


    def run(self):
        '''
        Clones given repo and renames destination to student real name if class roster is provided.
        '''
        try:            
            # If no commits, skip repo
            try:
                num_commits = len(list(self.__repo.get_commits()))
            except:
                print(f'{LIGHT_RED}Skipping `{self.__repo.name}` because it has 0 commits.{WHITE}')
                logging.warning(f'Skipping repo `{self.__repo.name}` because it has 0 commits.')
                return

            self.clone_repo() # clones repo
            commit_hash = self.get_commit_hash() # get commit hash at due date
            self.rollback_repo(commit_hash) # rollback repo to commit hash
            self.get_repo_stats() # get average lines per commit
        except IndexError as e: # Catch exception raised by get_repo_stats
                print(f'{LIGHT_RED}IndexError while finding average lines per commit for `{self.__repo.name}`.{WHITE}') # Print error to end user
                logging.warning(f'IndexError while finding average lines per commit for `{self.__repo.name}`.') # log warning to log file
        except: # Catch exception raised and interrupt main thread
            print(f'{LIGHT_RED}ERROR{WHITE}: Ran into a problem while cloning/resetting `{self.__repo.name}`, skipping. Check {LOG_FILE_PATH}.') # print error to end user
            logging.exception('ERROR:') # log error to log file (logging automatically is passed exception)


    def clone_repo(self):
        '''
        Clones a repo into the assignment folder.

        Due to some weird authentication issues. Git clone might need to have the github link with the token passed e.g.
        https://www.<token>@github.com/<organization>/<Repository.name>
        '''
        print(f'Cloning {self.__repo.name} into {self.__repo_path}...') # tell end user what repo is being cloned and where it is going to
        # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user
        clone_process = subprocess.Popen(['git', 'clone', self.__repo.clone_url, f'{str(self.__repo_path)}'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT) # git clone to output file, Hides output from console
        try:
            self.log_errors_given_subprocess(clone_process) # reads output line by line and checks for errors that occured during cloning
        except Exception as e:
            print(f'{LIGHT_RED}Skipping `{self.__repo.name}` because clone failed (likely due to invalid filename).{WHITE}') # print error to end user
            logging.warning(f'Skipping repo `{self.__repo.name}` because clone failed (likely due to invalid filename).') # log error to log file


    def get_commit_hash(self) -> str:
        '''
        Get commit hash at timestamp and reset local repo to timestamp on the default branch
        '''
        # run process on system that executes 'git rev-list' command. stdout is redirected so it doesn't output to end user
        rev_list_process = subprocess.Popen(['git', 'rev-list', '-n', '1', f'--before="{self.__date_due.strip()} {self.__time_due.strip()}"', f'origin/{self.__repo.default_branch}'], cwd=self.__repo_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with rev_list_process: # Read rev list output line by line to search for error or commit hash
            for line in iter(rev_list_process.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode()
                self.log_errors_given_line(line) # if command returned error raise exception
                return line.strip() # else returns commit hash of repo at timestamp
        

    def rollback_repo(self, commit_hash):
        '''
        Use commit hash and reset local repo to that commit (use git reset instead of git checkout to remove detached head warning)
        '''
        if not commit_hash:
            raise Exception('Invalid Commit hash. Usually caused by assignment not being accepted before due date/time.')
        # run process on system that executes 'git reset' command. stdout is redirected so it doesn't output to end user
        # git reset is similar to checkout but doesn't care about detached heads and is more forceful
        checkout_process = subprocess.Popen(['git', 'reset', '--hard', commit_hash], cwd=self.__repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            self.log_errors_given_subprocess(checkout_process)
        except Exception as e:
            print(f'{LIGHT_RED}Rollback failed for `{self.__repo.name}` (likely due to invalid filename at specified commit).{WHITE}')
            logging.warning(f'Rollback failed for `{self.__repo.name}` (likely due to invalid filename at specified commit).')
        

    def get_repo_stats(self):
        '''
        Get commit history stats and find average number of insertions per commit
        '''
        # run process on system that executes 'git log' command. stdout is redirected so it doesn't output to end user
        # output is something like this format:
        # <short commit hash> <commit message>
        #  <x> file(s) changed, <x> insertions(+)
        log_process = subprocess.Popen(['git', 'log', '--oneline', '--shortstat'], cwd=self.__repo_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # Loop through response line by line
        repo_stats = [] # list to store each commits insertion number
        with log_process:
            for line in iter(log_process.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode()
                self.log_errors_given_line(line)
                if (re.match(r"\s\d+\sfile.*changed,\s\d+\sinsertion.*[(+)].*", line)): # if line has insertion number in it
                    # Replaces all non digits in a string with nothing and appends the commit's stats to repo_stats list
                    # [0] = files changed
                    # [1] = insertions
                    # [2] = deletions (if any, might not be an index)
                    repo_stats.append([re.sub(r'\D', '', value) for value in line.strip().split(', ')])

        try:
            total_commits = len(repo_stats) # each index in repo_stats should be a commit
            total_insertions = 0
            # Loop through repos stats and find total number of insertions
            for i in range(total_commits):
                insertions = int(repo_stats[i][1])
                total_insertions += insertions
        except IndexError as e: # If an index error occurs for some reason, raise error
            raise e

        # Calc avg and place in global dictionary using maped repo name if student roster is provided or normal repo name
        average_insertions = round(total_insertions / total_commits, 2)
        if self.__student_filename: # If using a classroom roster, replace repo name in avgLinesInserted.txt w/ student name
            AVG_INSERTIONS_DICT[get_new_repo_name(self.__repo, self.__students, self.__assignment_name)] = average_insertions
        else: # else use default repo name
            AVG_INSERTIONS_DICT[self.__repo.name] = average_insertions


    def log_errors_given_subprocess(self, subprocess: subprocess):
        '''
        Reads full git command output of a subprocess and raises exception & logs if error is found
        '''
        with subprocess:
            for line in iter(subprocess.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode() # line is read in bytes. Decode to str
                if re.match(r'^error:|^warning:|^fatal:', line): # if git command threw error (usually wrong branch name)
                    logging.info('Subprocess: %r', line) # Log error
                    raise Exception(f'An error has occured with git.') # Raise exception to the thread

    
    def log_errors_given_line(self, line: str):
        '''
        Given 1 line of git command output, check if error.
        If so, log it and raise exception
        '''
        if re.match(r'^error:|^warning:|^fatal:', line): # if git command threw error (usually wrong branch name)
            logging.info('Subprocess: %r', line) # Log error to log file
            raise Exception(f'An error has occured with git.') # Raise exception to the thread


def get_repos(assignment_name: str, github_org_client: Organization) -> list:
    '''
    return list of all repos in an organization matching assignment name prefix
    '''
    return [repo for repo in github_org_client.get_repos() if assignment_name in repo.name]


def get_repos_specified_students(assignment_name: str, github_org_client: Organization, students: list) -> list:
    '''
    return list of all repos in an organization matching assignment name prefix and is a student specified in the specified class roster csv
    '''
    return [repo for repo in github_org_client.get_repos() if assignment_name in repo.name and is_student(repo, students) == True]


def get_students(student_filename: str) -> dict:
    '''
    Reads class roster csv in the format given by github classroom:
    "identifier","github_username","github_id","name"

    and returns a dictionary of students mapping github username to real name
    '''
    students = {} # student dict
    if opener(student_filename): # if classroom roster is found
        with open(student_filename) as f_handle: # use with to auto close file
            csv_reader = csv.reader(f_handle) # Use csv reader to separate values into a list
            next(csv_reader) # skip header line
            for student in csv_reader:
                name = re.sub(r'[. ]', '', re.sub(r'(, )|(,)', '-', student[0]).split(' ')[0])
                github = student[1]
                if name and github: # if csv contains student name and github username, map them to each other
                    students[github] = name
    else:
        raise FileNotFoundError(f'Classroom roster file `{student_filename}` not found.')
    return students # return dict mapping names to github username


def get_new_repo_name(repo: Repository, students: dict, assignment_name: str) -> str:
    '''
    Returns repo name replacing github username sufix with student's real name
    '''
    for student in students:
        if student in repo.name:
            return f'{assignment_name}-{students[student]}'
    return False


def is_student(repo: Repository, students: dict) -> bool:
    '''
    Check if repo belongs to one of the students in specified class roster
    '''
    for student in students:
        if student in repo.name:
            return True
    return False


def opener(file_name: str) -> bool:
    '''
    File opener for error handling. If file exists return true, else false
    '''
    try:
        with open(file_name) as f_handle:
            return True
    except FileNotFoundError:
        return False


def file_exists_handler(path):
    '''
    Attempts to remove file if it already exists attempt to remove it, if not exit with an error. If it doesn't exist, create it.
    '''
    if Path.is_dir(path):
        try:
            shutil.rmtree(path) # attempts to delete existing folder
            Path.mkdir(path)
        except:
            raise FileExistsError('Assignment file already exists. Delete and re-run script.')
    else:
        Path.mkdir(path)


def save_config(token: str, organization: Organization, use_classlist: bool, student_filename: str, output_dir: Path):
    '''
    Save parameters into config file to be read on future runs
    '''
    with open(CONFIG_PATH, 'w') as config:
        config.write(f'Token: {token}')
        config.write('\n')
        config.write(f'Organization: {organization}')
        config.write('\n')
        config.write(f'Save Classroom Roster: {str(use_classlist)}')
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
    use_classlist = ''
    student_filename = ''
    output_dir = ''
    if opener(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as config:
            token = config.readline().strip().split(': ')[1]
            organization = config.readline().strip().split(': ')[1]
            use_classlist = config.readline().strip().split(': ')[1]
            if use_classlist == 'True':
                use_classlist = True
                student_filename = config.readline().strip().split(': ')[1]
            elif use_classlist == 'False':
                use_classlist = False
                config.readline()
            output_dir = Path(config.readline().strip().split(': ')[1])
    return (token, organization, use_classlist, student_filename, output_dir)


def read_config() -> tuple:
    '''
    Checks whether config already exists, if so and use_classlist is False, ask for class roster path
    '''
    if opener(CONFIG_PATH): # If config already exists
        token, organization, use_classlist, student_filename, output_dir = read_config_raw() # get variables
        if use_classlist == False:
            print('OPTIONAL: Enter filename of csv file containing username and name of students. To ignore, just hit `enter`')
            student_filename = input('If ignored, repo names will not be changed to match student names: ')
            if student_filename: # if class roster was entered, set in config, check if use_classlist should be updated as well
                use_classlist = input('Use this every time? (can be changed later in tmp/config.txt) (Y/N): ')
                # Convert raw input boolean
                if 'y' in use_classlist.lower():
                    use_classlist = 'True'
                elif 'n' in use_classlist.lower():
                    use_classlist = 'False'
            else:
                use_classlist = 'False'
            save_config(token, organization, use_classlist, student_filename, output_dir)
    else:
        make_default_config()
        token, organization, use_classlist, student_filename, output_dir = read_config_raw() # Update return variables
    return (token, organization, student_filename, output_dir)


def make_default_config():
    '''
    Creates a default config file getting access token, org, class roster, etc, from user input
    '''
    use_classlist = ''
    student_filename = ''
    token = input('Github Authentication Token: ')
    organization = input('Organization Name: ')
    print('OPTIONAL: Enter filename of csv file containing username and name of students. To ignore, just hit `enter`')
    student_filename = input('If ignored, repo names will not be changed to match student names: ')
    if student_filename:
        use_classlist = input('Use this every time? (can be changed later in tmp/config.txt) (Y/N): ')
        # Convert raw input to boolean
        if 'y' in use_classlist.lower():
            use_classlist = 'True'
        elif 'n' in use_classlist.lower():
            use_classlist = 'False'
    else:
        use_classlist = 'False'
    output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))
    if not output_dir:
        output_dir = Path.cwd()
    while not Path.is_dir(output_dir):
        print(f'Directory `{output_dir}` not found.')
        output_dir = Path(input('Output directory for assignment files (`enter` for current directory): '))
    save_config(token, organization, use_classlist, student_filename, output_dir)


def check_git_version():
    '''
    Check that git version is at or above min requirements for script
    '''
    try:
        git_version = subprocess.check_output(['git', '--version'], stderr=subprocess.PIPE).decode().strip()[12:16]
        if float(git_version) < MIN_GIT_VERSION:
            raise ValueError(f'Your version of git is not compatible with this script. Use version {MIN_GIT_VERSION}+.')
    except FileNotFoundError:
        raise NotImplementedError('git not installed on the path.')



def check_pygithub_version():
    '''
    Check that PyGithub version is at or above min requirements for script
    '''
    version = 0.0
    try:
        check_pygithub_version_process = subprocess.Popen(['pip', 'show', 'pygithub'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with check_pygithub_version_process:
            for line in iter(check_pygithub_version_process.stdout.readline, b''): # b'\n'-separated lines
                line = line.decode().lower()
                if 'version:' in line:
                    version = float(line.split(': ')[1][0:4])
            if version < MIN_PYGITHUB_VERSION:
                raise ValueError(f'Incompatible PyGithub version. Use version {MIN_PYGITHUB_VERSION}+. Use `pip install PyGithub --upgrade` to update')
    except FileNotFoundError:
        raise NotImplementedError('pip not installed on the path.')


def write_avg_insersions_file(initial_path, assignment_name):
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


def main():
    '''
    Main function
    '''
    # Enable color in cmd
    if os.name == 'nt':
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

        # Create Organization to access repos
        git_org_client = Github(token.strip(), pool_size = MAX_THREADS).get_organization(organization.strip())

        # Variables used to get proper repos
        assignment_name = input('Assignment Name: ') # get assignment name (repo prefix)
        while not assignment_name: # if input is empty ask again
            assignment_name = input('Please input an assignment name: ')
        date_due = input('Date Due (format = yyyy-mm-dd, press `enter` for current): ') # get due date
        if not date_due: # If due date is blank use current date
            current_date = date.today() # get current date
            date_due = current_date.strftime('%Y-%m-%d') # get current date in year-month-day format
            print(f'Using current date: {date_due}') # output what is being used to end user
        time_due = input('Time Due (24hr, press `enter` for current): ') # get time assignment was due
        if not time_due: # if time due is blank use current time
            current_time = datetime.now() # get current time
            time_due = current_time.strftime('%H:%M') # format current time into hour:minute 24hr format
            print(f'Using current date: {time_due}') # output what is being used to end user
        print() # new line for formatting reasons

        # If student roster is specified, get repos list using proper function
        students = dict() # student dict variable do be used im main scope
        if student_filename: # if classroom roster is specified use it
            students = get_students(student_filename) # fill student dict
            repos = get_repos_specified_students(assignment_name, git_org_client, students)
        else:
            repos = get_repos(assignment_name, git_org_client)

        # Sets path to output directory inside assignment folder where repos will be cloned
        initial_path = output_dir / assignment_name

        # Makes parent folder for whole assignment. Raises eror if file already exists and it cannot be deleted
        file_exists_handler(initial_path)

        threads = []
        # goes through list of repos and clones them into the assignment's parent folder
        for repo in repos:
            # Create thread to handle repos and add to thread list
            # Each thread clones a repo, sets it back to due date/time, and gets avg lines per commit
            thread = RepoHandler(repo, assignment_name, date_due, time_due, students, bool(student_filename), initial_path)
            threads += [thread]

        # Run all clone threads
        for thread in threads:
            thread.start()

        # Make main thread wait for all repos to be cloned, set back to due date/time, and avg lines per commit to be found
        for thread in threads:
            thread.join()

        num_of_lines = write_avg_insersions_file(initial_path, assignment_name)
        print()
        print(f'{LIGHT_GREEN}Done.{WHITE}')
        print(f'{LIGHT_GREEN}Cloned {len(next(os.walk(initial_path))[1])}/{len(repos)} repos.{WHITE}')
        print(f'{LIGHT_GREEN}Found average lines per commit for {num_of_lines}/{len(repos)} repos.{WHITE}')
    except FileNotFoundError as e: # If classroom roster file specified in config.txt isn't found.
        print()
        print(f'Classroom roster `{student_filename}` not found.')
        logging.error(e)
    except FileExistsError as e: # Error thrown if parent assignment file already exists
        print()
        print(f'ERROR: File `{initial_path}` already exists, please delete it and run again')
        logging.error(e)
    except KeyboardInterrupt as e: # When thread fails because subprocess command threw some error/exception
        print()
        print('ERROR: Something happened during the cloning process; your repos are not at the proper timestamp. Delete the assignment folder and run again.')
        logging.error(e)
    except ValueError as e: # When git version is incompatible w/ script
        print()
        print(e)
        logging.error(e)
    except NotImplementedError as e:
        print()
        print(e)
        logging.error(e)
    except Exception as e: # If anything else happens
        print(f'ERROR: Something happened. Check {LOG_FILE_PATH}')
        logging.error(e)
    exit()


if __name__ == '__main__':
    main()
