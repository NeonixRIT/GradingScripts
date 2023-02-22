import subprocess
import os
import sys
import requests
import zipfile

from pathlib import Path

LIGHT_GREEN = '\033[1;32m'
LIGHT_RED = '\033[1;31m'
CYAN = '\u001b[36m'
WHITE = '\033[0m'

update_with_git = False
update_with_download = False

if Path(sys.argv[2] + '/.git').exists():
    update_with_git = True
else:
    update_with_download = True


def onerror(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def download_and_update(save_path):
    version = sys.argv[1]
    script_location = sys.argv[2]
    url = f'https://github.com/NeonixRIT/GradingScripts/archive/refs/tags/{version}.zip'
    resp = requests.get(url, stream=True)
    with open(save_path, 'wb') as fd:
        for chunk in resp.iter_content(chunk_size=128):
            fd.write(chunk)

    zip_file = zipfile.ZipFile(save_path)
    zip_file.extractall()
    zip_file.close()

    import shutil
    source = f'./GradingScripts-{version}/'
    allfiles = os.listdir(source)
    for f in allfiles:
        if 'data' in f:
            continue
        src_path = os.path.join(source, f)
        dst_path = os.path.join(script_location, f)
        if Path(dst_path).exists():
            if Path(dst_path).is_dir():
                shutil.rmtree(dst_path, onerror=onerror)
            else:
                os.remove(dst_path)
        shutil.move(src_path, dst_path)
    os.remove(save_path)
    shutil.rmtree(source, onerror=onerror)


if update_with_git:
    try:
        version = sys.argv[1]
        subprocess.run(['git', 'fetch', 'origin'], cwd=sys.argv[2], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        subprocess.run(['git', 'reset', '--hard', version], cwd=sys.argv[2], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    except Exception as e:
        print(f'{LIGHT_RED}FATAL: Exception occured while trying to update:{WHITE}\n\t{e}')
        print('Unable to complete auto update.')
        input('Press enter to exit...')
        exit()
elif update_with_download:
    download_and_update(f'./GCISGradingScript-temp-{sys.argv[1]}.zip')

subprocess.run([sys.executable, './GCISScripts.py'], cwd=sys.argv[2])
