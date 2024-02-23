import json
import os
import shutil
import time

from tuiframeworkpy import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE, clear

from types import SimpleNamespace
from pathlib import Path


# new config/log location = \data
# check for \tmp and import settings to new json config if exists
# verify settings
# verify pip packages if not installed ask if want to install them
def search_old_config() -> str:
    if not Path('./tmp').exists():
        return ''

    for file in os.listdir('./tmp'):
        if 'config.txt' in file:
            return str(Path('./tmp') / Path(file))
    return ''


def search_new_config() -> bool:
    if not Path('./tmp').exists():
        return ''

    for file in os.listdir('./data'):
        if 'config.json' in file:
            return file
    return ''


def read_old_config_raw(old_config_path: str) -> dict:
    """
    Reads config containing token, organization, whether to use class list, and path of class list.
    Return values as tuple
    """
    token = ''
    organization = ''
    student_filename = ''
    output_dir = ''
    if Path(old_config_path).exists():
        with open(old_config_path, 'r') as config:
            token = config.readline().strip().split(': ')[1]
            organization = config.readline().strip().split(': ')[1]
            _ = config.readline().strip().split(': ')[1]
            student_filename = config.readline().strip().split(': ')[1]
            output_dir = config.readline().strip().split(': ')[1]
    return {
        'token': token,
        'organization': organization,
        'students_csv': student_filename,
        'out_dir': output_dir,
    }


def setup(config_manager) -> None:
    clear()
    if search_new_config():
        print(
            f'{LIGHT_RED}WARNING:{WHITE} Current config file detected. Running setup will overwrite current config file.'
        )
        confimation = input(
            f'Do you still wish to continue ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? '
        ).lower()
        if not confimation == 'y' or confimation == 'yes':
            clear()
            return

    start = time.perf_counter()
    old_config_path = search_old_config()
    found = time.perf_counter() - start
    if not old_config_path:
        clear()
        config = config_manager.make_new_config()
        config_manager.save_config(config)
        return

    confimation = input(
        f'Legacy config file found. Would you like to import these settings ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? '
    ).lower()
    if not confimation == 'y' or confimation == 'yes':
        clear()
        config = config_manager.make_new_config()
        config_manager.save_config(config)
        return

    start2 = time.perf_counter()
    old_values = read_old_config_raw(old_config_path)
    old_values_formatted = json.dumps(old_values, indent=4)
    config = json.loads(
        old_values_formatted, object_hook=lambda d: SimpleNamespace(**d)
    )
    try:
        shutil.copyfile(
            config.students_csv, f'./data/csvs/{config.students_csv.split("/")[-1]}'
        )
        config.students_csv = f'./data/csvs/{config.students_csv.split("/")[-1]}'
    except Exception:  # if run into error its fine this just QOL feature
        pass
    config.presets = []
    config.add_rollback = []
    config_manager.save_config(config)
    imported = time.perf_counter() - start2
    print(
        f'{LIGHT_GREEN}Legacy values found and imported in {round((found + imported) * 1000, 1)} milliseconds.{WHITE}'
    )
