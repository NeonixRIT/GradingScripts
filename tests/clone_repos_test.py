import io
import logging
import os
import pytest

import clone_repos as rh
import github as git

from datetime import date, datetime
from enum import Enum
from pathlib import Path

rh.CONFIG_PATH = './test_config.txt'
rh.LOG_FILE_PATH = './test_log.log'
REG_CONFIG_PATH = '../tmp/config.txt'
TEMP_OUT_DIR = 'exists_01_14_18_45'
ROSTER_FILENAME = 'test_roster.csv'
DATE = '2022-01-14'
TIME = '18:45'
ASSIGNMENT_NAME = 'test'
ORGANIZATION_NAME = 'GradingScriptsTest'
TOKEN = open(REG_CONFIG_PATH).readline().split(': ')[1].strip()
logging.basicConfig(level=logging.INFO, filename=rh.LOG_FILE_PATH)


class Result(Enum):
    PASS = True
    FAIL = False


def find_repo_by_name(repos, repo_name):
    return [repo for repo in repos if repo_name == repo.name][0]


def repo_handler_setup(repo_name):
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    repos = rh.get_repos_specified_students(repo_gen, students, ASSIGNMENT_NAME)
    initial_path = Path(f'./{TEMP_OUT_DIR}/')
    return rh.RepoHandler(find_repo_by_name(repos, repo_name), ASSIGNMENT_NAME, DATE, TIME, students, initial_path, TOKEN)


'''clone_repos Tests'''
def test_is_windows_true():
    expected = True
    actual = rh.is_windows()
    assert actual == expected


def test_is_windows_false():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    # expected = False
    # actual = rh.is_windows()
    # assert actual == expected
    pass


def test_build_init_path():
    output_dir = Path('.')
    expected = Path('./test_01_14_18_45')
    actual = rh.build_init_path(output_dir, ASSIGNMENT_NAME, DATE, TIME)
    assert actual == expected
    
    
def test_build_init_path_exists():
    output_dir = Path('.')
    expected = Path(f'./{TEMP_OUT_DIR}_iter_1')
    actual = rh.build_init_path(output_dir, 'exists', DATE, TIME)
    assert actual == expected


def test_get_repos():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    repos = []
    for repo in repo_gen:
        repos.append(repo.name)
        
    expected = sorted(['test-late-accept', 'test-main-branch', 'test-base', 'test-master-branch', 'test-weird-commit', 'test-NoDash', 'test-bad-filename', 'test', 'test-bad-filename-rollback'])
    actual = sorted(repos)
    assert actual == expected
        

def test_get_students():
    expected = sorted({
        'AcheronsS': 'Student-Multiple-Names-Test-M-I',
        'late-accept': 'accept-late',
        'base': 'student-base',
        'master-branch': 'branch-master',
        'main-branch': 'branch-main',
        'NoDash': 'no,dash',
        'weird-commit': 'weird-commit',
        'bad-filename': 'bad-filename',
        'bad-filename-rollback': 'bad-filename-rollback'
    })
    actual = sorted(rh.get_students(ROSTER_FILENAME))
    assert actual == expected


def test_get_repos_specified_students():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    expected = sorted({'test-late-accept', 'test-main-branch', 'test-base', 'test-master-branch', 'test-weird-commit', 'test-NoDash', 'test-bad-filename', 'test-bad-filename-rollback'})
    actual = sorted([repo.name for repo in rh.get_repos_specified_students(repo_gen, students, ASSIGNMENT_NAME)])
    assert actual == expected


def test_get_new_repo_name():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    base_name = 'test-base'
    expected = 'test-student-base'
    actual = rh.get_new_repo_name(find_repo_by_name(repo_gen, base_name), students, ASSIGNMENT_NAME)
    assert actual == expected


def test_read_config_exists():
    exp_token = 'PlaceHolderToken'
    exp_organization = 'PlaceHolderOrg'
    exp_student_filename = 'PlaceHolderPath'
    exp_output_dir = Path(TEMP_OUT_DIR)
    act_token, act_organization, act_student_filename, act_output_dir = rh.read_config()
    assert (act_token, act_organization, act_student_filename, act_output_dir) == (exp_token, exp_organization, exp_student_filename, exp_output_dir)


def test_read_config_not_exists(monkeypatch):
    rh.CONFIG_PATH = 'NotExist_Config.txt'
    exp_token = 'PlaceHolderToken'
    exp_organization = 'PlaceHolderOrg'
    exp_student_filename = 'PlaceHolderPath'
    exp_output_dir = Path(TEMP_OUT_DIR)
    monkeypatch.setattr('sys.stdin', io.StringIO(f'{exp_token}\n{exp_organization}\n{exp_student_filename}\n{exp_output_dir}'))
    act_token, act_organization, act_student_filename, act_output_dir = rh.read_config()
    assert (act_token, act_organization, act_student_filename, act_output_dir) == (exp_token, exp_organization, exp_student_filename, exp_output_dir)
    os.remove('NotExist_Config.txt')


def test_check_git_version_good():
    try:
        rh.check_git_version()
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_git_version_bad():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    # try:
    #     rh.check_git_version()
    #     assert Result.FAIL
    # except (rh.InvalidGitVersion, FileNotFoundError):
    #     assert Result.PASS
    # except Exception:
    #     assert Result.FAIL
    pass


def test_check_pygithub_version_good():
    try:
        rh.check_pygithub_version()
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_pygithub_version_bad():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    # try:
    #     rh.check_pygithub_version()
    #     assert Result.FAIL
    # except (rh.InvalidPyGithubVersion, FileNotFoundError):
    #     assert Result.PASS
    # except Exception:
    #     assert Result.FAIL
    pass


def test_check_date_good():
    try:
        rh.check_date(DATE)
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_date_bad():
    try:
        rh.check_date('2022/01/14')
        assert Result.FAIL
    except rh.InvalidDate:
        assert Result.PASS
    except Exception:
        assert Result.FAIL
    
    
def test_check_time_good():
    try:
        rh.check_time(TIME)
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_time_bad():
    try:
        rh.check_time('8:30')
        assert Result.FAIL
    except rh.InvalidTime:
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_assignment_good():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    try:
        rh.check_assignment_name([repo for repo in repo_gen])
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_check_assignment_bad():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos('Not Real Assignment', org_repos)
    try:
        rh.check_assignment_name([repo for repo in repo_gen])
        assert Result.FAIL
    except rh.InvalidAssignmentName:
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_attempt_get_assignment(monkeypatch):
    empty_string = ''
    monkeypatch.setattr('sys.stdin', io.StringIO(f'{empty_string}\n{ASSIGNMENT_NAME}'))
    expected = ASSIGNMENT_NAME
    actual = rh.attempt_get_assignment()
    assert actual == expected


def test_get_time(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(f'{TIME}'))
    expected = TIME
    actual = rh.get_time()
    assert actual == expected


def test_get_time_empty(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(f'\n'))
    expected = datetime.now().strftime('%H:%M') # get current time
    actual = rh.get_time()
    assert actual == expected


def test_get_date(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(f'{DATE}'))
    expected = DATE
    actual = rh.get_date()
    assert actual == expected


def test_get_date(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(f'\n'))
    expected = date.today().strftime('%Y-%m-%d')
    actual = rh.get_date()
    assert actual == expected


def test_find_students_not_accepted():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    repos = rh.get_repos_specified_students(repo_gen, students, ASSIGNMENT_NAME)
    expected = {'AcheronsS'}
    actual = rh.find_students_not_accepted(students, repos, ASSIGNMENT_NAME)
    assert actual == expected


def test_attempt_make_client_valid():
    try:
        rh.attempt_make_client(TOKEN, ORGANIZATION_NAME, ROSTER_FILENAME, output_dir='.')
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_attempt_make_client_inv_tok(monkeypatch):
    try:
        monkeypatch.setattr('sys.stdin', io.StringIO(f'y\n{TOKEN}'))
        rh.attempt_make_client('INVALID_TOKEN', ORGANIZATION_NAME, ROSTER_FILENAME, output_dir='.')
        assert Result.PASS
    except Exception:
        assert Result.FAIL
    os.remove('NotExist_Config.txt')


def test_attempt_make_client_inv_org(monkeypatch):
    try:
        monkeypatch.setattr('sys.stdin', io.StringIO(f'y\n{ORGANIZATION_NAME}'))
        rh.attempt_make_client(TOKEN, 'INVALID_ORG', ROSTER_FILENAME, output_dir='.')
        assert Result.PASS
    except Exception:
        assert Result.FAIL
    os.remove('NotExist_Config.txt')


def test_attempt_make_client_inv_no(monkeypatch):
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        monkeypatch.setattr('sys.stdin', io.StringIO(f'n'))
        rh.attempt_make_client(TOKEN, 'INVALID_ORG', ROSTER_FILENAME, output_dir='.')
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 42
        assert Result.FAIL


def test_print_end_report(capsys):
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    repos = rh.get_repos_specified_students(repo_gen, students, ASSIGNMENT_NAME)
    not_accepted = rh.find_students_not_accepted(students, repos, ASSIGNMENT_NAME)
    cloned_num = 5
    rolled_back_num = 5
    lines_written = 5
    rh.print_end_report(students, repos, len(not_accepted), cloned_num, rolled_back_num, lines_written)
    expected = '\n\x1b[1;32mDone.\x1b[0m\n\x1b[1;32m\x1b[1;31m8\x1b[0m\x1b[1;32m/9 accepted the assignment.\x1b[0m\n\x1b[1;32mCloned \x1b[1;31m5\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n\x1b[1;32mRolled Back \x1b[1;31m5\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n\x1b[1;32mFound average lines per commit for \x1b[1;31m5\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n'
    actual = capsys.readouterr().out
    assert actual == expected


def check_update_available_true():
    rh.SCRIPT_VERSION = '0.0.0'
    expected = True
    actual = rh.check_update_available(TOKEN)
    assert actual == expected


def check_update_available_false():
    rh.SCRIPT_VERSION = f'9999.9999.9999'
    expected = False
    actual = rh.check_update_available(TOKEN)
    assert actual == expected


''' RepoHandler() Tests'''
def test_repo_base():
    try:
        repo_handler_setup('test-base').run_raise()
        assert Result.PASS
    except Exception:
        assert Result.FAIL

def test_master_branch():
    try:
        repo_handler_setup('test-master-branch').run_raise()
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_main_branch():
    try:
        repo_handler_setup('test-main-branch').run_raise()
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_repo_no_dash():
    try:
        repo_handler_setup('test-NoDash').run_raise()
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_repo_bad_filename():
    try:
        repo_handler_setup('test-bad-filename').run_raise()
    except rh.CloneException:
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_repo_bad_filename_rollback():
    try:
        repo_handler_setup('test-bad-filename-rollback').run_raise()
        assert Result.FAIL
    except rh.RollbackException:
        assert Result.PASS


def test_weird_commit_msg():
    repo_handler_setup('test-weird-commit').run_raise()
    expected = 1.33
    actual = rh.AVG_INSERTIONS_DICT['test-weird-commit']
    assert actual == expected


def test_repo_late():
    try:
        repo_handler_setup('test-late-accept').run_raise()
        assert Result.FAIL
    except rh.RollbackException:
        assert Result.PASS
