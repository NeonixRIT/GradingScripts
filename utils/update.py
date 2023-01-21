import os
import subprocess
import sys

from pathlib import Path


def spawn_program_and_die(program, exit_code=0):
    subprocess.Popen(program)
    sys.exit(exit_code)


update_with_git = False
update_with_download = False

if Path('../.git').exists():
    update_with_git = True
else:
    update_with_download = True


if update_with_git:
    try:
        subprocess.run('git fetch origin', cwd='../', stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        subprocess.run('git reset --hard origin/master', cwd='../', stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    except Exception as e:
        print('Unable to complete auto update.')
        exit()
    print('Update was a success.')
    spawn_program_and_die([sys.executable, '../GCISScripts.py'])
