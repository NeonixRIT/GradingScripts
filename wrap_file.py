from sys import argv, exit
from os import system, path
from subprocess import check_output
from PyInstaller.__main__ import run

argv = ['', 'cat']
path_to_cmd = check_output(['which', argv[1]]).decode('utf-8').strip()
new_path_to_cmd = f'/tmp{path_to_cmd}'
if path.exists(new_path_to_cmd):
    exit(1)


script = '''
import sys
from os import system
sys.argv = sys.argv[1:]
def error_handler(exc_type, exc_value, exc_traceback):
    print(str(exec_value).replace('/tmp', ''))
sys.excepthook = error_handler
cmd_suffix = '> /dev/null 2>&1'
cmds = ["echo 'hello from wrapper'"]
path_to_cmd = "%%PATH%%"
[system(f"{cmd}") for cmd in cmds]
system(f"{path_to_cmd} {chr(32).join(sys.argv)}")
'''.replace('%%PATH%%', new_path_to_cmd)

with open(f'{argv[1]}.py', 'w') as f:
    f.write(script)

run(['--onefile', '--clean', f'./{argv[1]}.py'])
system(f'rm -f {argv[1]}.py')
system(f'sudo mkdir -p {new_path_to_cmd.replace(argv[1], "")}')
system(f'sudo mv {path_to_cmd} {new_path_to_cmd.replace(argv[1], "")}')
system(f'sudo mv ./dist/{argv[1]} {path_to_cmd.replace(argv[1], "")}')
system(f'sudo chmod 777 {path_to_cmd}')
system(f'sudo chmod 777 {new_path_to_cmd}')
system(f'sudo chown root:root {path_to_cmd}')