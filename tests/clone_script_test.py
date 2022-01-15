import logging

import clone_repos as rh
import clone_script as rhs

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


def test_print_help_1(capsys):
    expected = 'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]\n    <assignment name>:    Set assignment name. Same as repo prefix in organization\n    <due date>:           due date of assignment in yyyy-mm-dd format.\n    <due time>:           due time of assignment in HH:MM 24hr format.\n    [folder name]:        OPTIONAL. Changes output folder name from default assignment name\n\n\x1b[1;31minvalid number of arguments\x1b[0m\n'
    args = ['clone_script.py', '-h']
    try:
        rhs.main(args)
    except rh.InvalidArguments:
        pass
    actual = capsys.readouterr().out
    assert actual == expected


def test_print_help_2(capsys):
    expected = 'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]\n    <assignment name>:    Set assignment name. Same as repo prefix in organization\n    <due date>:           due date of assignment in yyyy-mm-dd format.\n    <due time>:           due time of assignment in HH:MM 24hr format.\n    [folder name]:        OPTIONAL. Changes output folder name from default assignment name\n\n\x1b[1;31minvalid number of arguments\x1b[0m\n'
    args = ['clone_script.py', '-help']
    try:
        rhs.main(args)
    except rh.InvalidArguments:
        pass
    actual = capsys.readouterr().out
    assert actual == expected


def test_print_help_3(capsys):
    expected = 'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]\n    <assignment name>:    Set assignment name. Same as repo prefix in organization\n    <due date>:           due date of assignment in yyyy-mm-dd format.\n    <due time>:           due time of assignment in HH:MM 24hr format.\n    [folder name]:        OPTIONAL. Changes output folder name from default assignment name\n\n\x1b[1;31minvalid number of arguments\x1b[0m\n'
    args = ['clone_script.py', '-?']
    try:
        rhs.main(args)
    except rh.InvalidArguments:
        pass
    actual = capsys.readouterr().out
    assert actual == expected


def test_print_help_4(capsys):
    expected = 'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]\n    <assignment name>:    Set assignment name. Same as repo prefix in organization\n    <due date>:           due date of assignment in yyyy-mm-dd format.\n    <due time>:           due time of assignment in HH:MM 24hr format.\n    [folder name]:        OPTIONAL. Changes output folder name from default assignment name\n\n\x1b[1;31minvalid number of arguments\x1b[0m\n'
    args = ['clone_script.py', '?']
    try:
        rhs.main(args)
    except rh.InvalidArguments:
        pass
    actual = capsys.readouterr().out
    assert actual == expected


def test_parse_args_3():
    try:
        args = ['clone_script.py', ASSIGNMENT_NAME, DATE]
        rhs.parse_args(args)
        assert Result.FAIL
    except rh.InvalidArguments:
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_parse_args_4():
    args = ['clone_script.py', ASSIGNMENT_NAME, DATE, TIME]
    assignment_name, date_due, time_due, out_folder = rhs.parse_args(args)
    assert (assignment_name, date_due, time_due, out_folder) == (args[1], args[2], args[3], '')


def test_parse_args_5():
    args = ['clone_script.py', ASSIGNMENT_NAME, DATE, TIME, TEMP_OUT_DIR]
    assignment_name, date_due, time_due, out_folder = rhs.parse_args(args)
    assert (assignment_name, date_due, time_due, out_folder) == (args[1], args[2], args[3], args[4])


def test_parse_args_6():
    try:
        args = ['clone_script.py', ASSIGNMENT_NAME, DATE, TIME, TEMP_OUT_DIR, 'extra_arg']
        rhs.parse_args(args)
        assert Result.FAIL
    except rh.InvalidArguments:
        assert Result.PASS
    except Exception:
        assert Result.FAIL


def test_build_init_path_given_out():
    output_dir = Path('.')
    expected = Path('./test_01_14_18_45')
    actual = rhs.build_init_path_given_out(output_dir, 'test_01_14_18_45')
    assert actual == expected


def test_build_init_path_given_out_exists():
    output_dir = Path('.')
    expected = Path(f'./{TEMP_OUT_DIR}_iter_1')
    actual = rhs.build_init_path_given_out(output_dir, TEMP_OUT_DIR)
    assert actual == expected


def test_main(capsys):
    expected = sorted('\x1b[1;31m`Student-Multiple-Names-Test-M-I` (AcheronsS) did not accept the assignment.\x1b[0m\n\nCloning test-main-branch into exists_01_14_18_45\\exists_01_14_18_45\\test-branch-main...\nCloning test-master-branch into exists_01_14_18_45\\exists_01_14_18_45\\test-branch-master...\nCloning test-late-accept into exists_01_14_18_45\\exists_01_14_18_45\\test-accept-late...\nCloning test-base into exists_01_14_18_45\\exists_01_14_18_45\\test-student-base...\nCloning test-NoDash into exists_01_14_18_45\\exists_01_14_18_45\\test-no-dash...\nCloning test-bad-filename into exists_01_14_18_45\\exists_01_14_18_45\\test-bad-filename...\nCloning test-bad-filename-rollback into exists_01_14_18_45\\exists_01_14_18_45\\test-bad-filename-rollback...\nCloning test-weird-commit into exists_01_14_18_45\\exists_01_14_18_45\\test-weird-commit...\n\x1b[1;31mSkipping repo `test-bad-filename` because: Clone failed (likely due to invalid filename).\x1b[0m\n\x1b[1;31mSkipping repo `test-late-accept` because: Invalid commit hash (likely due to student accepting assignment after given date/time).\x1b[0m\n\x1b[1;31mSkipping repo `test-bad-filename-rollback` because: Rollback failed for `test-bad-filename-rollback` (likely due to invalid filename at specified commit).\x1b[0m\n\n\x1b[1;32mDone.\x1b[0m\n\x1b[1;32m\x1b[1;31m8\x1b[0m\x1b[1;32m/9 accepted the assignment.\x1b[0m\n\x1b[1;32mCloned \x1b[1;31m14\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n\x1b[1;32mRolled Back \x1b[1;31m10\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n\x1b[1;32mFound average lines per commit for \x1b[1;31m5\x1b[0m\x1b[1;32m/8 repos.\x1b[0m\n'.split('\n'))
    args = ['clone_script.py', ASSIGNMENT_NAME, DATE, TIME, TEMP_OUT_DIR]
    rhs.main(args, TOKEN, ORGANIZATION_NAME, ROSTER_FILENAME)
    actual = sorted(capsys.readouterr().out.split('\n'))
    assert actual == expected
