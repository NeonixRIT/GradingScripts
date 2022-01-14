import clone_repos as rh
import github as git

from pathlib import Path

REG_CONFIG_PATH = '../tmp/config.txt'
ROSTER_FILENAME = 'test_roster.csv'
DATE = '2022-01-14'
TIME = '08:30'
ASSIGNMENT_NAME = 'test'
ORGANIZATION_NAME = 'GradingScriptsTest'
TOKEN = open(REG_CONFIG_PATH).readline().split(': ')[1]

'''clone_repos Tests'''
def test_is_windows_true():
    expected = True
    actual = rh.is_windows()
    assert actual == expected


def test_is_windows_false():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    pass


def test_build_init_path():
    output_dir = Path('.')
    
    expected = Path('./test_01_14_08_30')
    actual = rh.build_init_path(output_dir, ASSIGNMENT_NAME, DATE, TIME)
    assert actual == expected
    
    
def test_build_init_path_exists():
    output_dir = Path('.')
    
    expected = Path('./exists_01_14_08_30_iter_1')
    actual = rh.build_init_path(output_dir, 'exists', DATE, TIME)
    assert actual == expected


def test_get_repos():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    repos = []
    for repo in repo_gen:
        repos.append(repo.name)
        
    expected = sorted(['test-late-accept', 'test-main-branch', 'test-base', 'test-master-branch', 'test-weird-commit', 'test-NoDash', 'test-bad-filename', 'test'])
    actual = sorted(repos)
    assert actual == expected
        

def test_get_students():
    expected = sorted({
        "AcheronsS": "Student-Multiple-Names-Test-M-I",
        "late-accept": "accept-late",
        "base": "student-base",
        "master-branch": "branch-master",
        "main-branch": "branch-main",
        "NoDash": "no,dash",
        "weird-commit": "weird-commit",
        "bad-filename": "bad-filename"
    })
    actual = sorted(rh.get_students(ROSTER_FILENAME))
    assert actual == expected


def test_get_repos_specified_students():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    org_repos = github_client.get_repos()
    repo_gen = rh.get_repos(ASSIGNMENT_NAME, org_repos)
    students = rh.get_students(ROSTER_FILENAME)
    expected = sorted({'test-late-accept', 'test-main-branch', 'test-base', 'test-master-branch', 'test-weird-commit', 'test-NoDash', 'test-bad-filename'})
    actual = sorted([repo.name for repo in rh.get_repos_specified_students(repo_gen, students, ASSIGNMENT_NAME)])
    assert actual == expected


def test_get_new_repo_name():
    pass


def test_read_config_exists():
    pass


def test_read_config_not_exists():
    pass


def check_git_version_good():
    pass


def check_git_version_bad():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    pass


def check_pygithub_version_good():
    pass


def check_pygithub_version_bad():
    '''DONT HAVE ENVIRONMENT TO TEST'''
    pass


def test_check_date_good():
    pass


def test_check_date_bad():
    pass
    
    
def test_check_time_good():
    pass


def test_check_time_bad():
    pass


def test_check_assignment_good():
    pass


def test_check_assignment_bad():
    pass


def test_attempt_get_assignment():
    pass


def test_get_time():
    pass


def test_get_date():
    pass


def test_find_students_not_accepted():
    pass


def test_attempt_make_client_valid():
    pass


def test_attempt_make_client_inv_tok():
    pass


def test_attempt_make_client_inv_org():
    pass


def test_print_end_report():
    pass


def test_log_timing_report():
    pass


''' RepoHandler Tests'''
def test_repo_base():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_master_branch():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_main_branch():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_repo_no_dash():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_repo_bad_filename():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_weird_commit_msg():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()


def test_repo_late():
    github_client = git.Github(TOKEN.strip(), pool_size = rh.MAX_THREADS).get_organization(ORGANIZATION_NAME)
    repo_handler = RepoHandler()