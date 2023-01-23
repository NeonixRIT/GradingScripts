import subprocess
import os
import sys
import requests
import zipfile

from pathlib import Path

update_with_git = False
update_with_download = False

if Path('../.git').exists():
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

    import shutil
    source = f'./GradingScripts-{version}/'
    allfiles = os.listdir(source)
    for f in allfiles:
        src_path = os.path.join(source, f)
        dst_path = os.path.join(script_location, f)
        if Path(dst_path).exists():
            if Path(dst_path).is_dir():
                shutil.rmtree(dst_path, onerror=onerror)
            else:
                os.remove(dst_path)
        shutil.move(src_path, dst_path)
    shutil.rmtree(save_path, onerror=onerror)
    shutil.rmtree(source, onerror=onerror)


if update_with_git:
    try:
        subprocess.run(['git', 'fetch', 'origin'], cwd='../', stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        subprocess.run(['git', 'reset', '--hard', 'origin/master'], cwd='../', stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    except Exception as e:
        print('Unable to complete auto update.')
        exit()
    print('Update was a success.')
    subprocess.run([sys.executable, '../GCISScripts.py'], cwd='../')
