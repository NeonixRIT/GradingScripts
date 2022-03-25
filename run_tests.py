import os
import pathlib
import pytest
import shutil

import clone_repos as rh

TEMP_OUT_DIR = 'exists_01_14_18_45'


def onerror(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def test_setup():
    if not pathlib.Path('test_log.log').exists():
        open('test_log.log', 'w').close()

    if pathlib.Path(TEMP_OUT_DIR).exists():
        shutil.rmtree(f'./{TEMP_OUT_DIR}', onerror=onerror)
        os.mkdir(TEMP_OUT_DIR)
    else:
        os.mkdir(TEMP_OUT_DIR)


def run_clone_repos_tests():
    pytest.main(['--asyncio-mode=strict', '-vv', 'clone_repos_test.py'])


def run_clone_script_tests():
    pytest.main(['--asyncio-mode=strict', '-vv', 'clone_script_test.py'])


def cleanup():
    import shutil
    try:
        os.remove(rh.LOG_FILE_PATH)
        shutil.rmtree(f'./{TEMP_OUT_DIR}', onerror=onerror)
    except FileNotFoundError:
        print('Something went wrong :).')


def run_test(test_func):
    test_setup()
    test_func()
    cleanup()


def main():
    os.chdir(pathlib.Path.cwd() / 'tests')
    run_test(run_clone_repos_tests)
    run_test(run_clone_script_tests)


if __name__ == '__main__':
    main()
