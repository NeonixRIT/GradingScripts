# prompt for folder containing repos
# find and store path of folders with .git in them
# load files into memory
import asyncio
import os
import shutil

from model.colors import LIGHT_RED, LIGHT_GREEN, CYAN, WHITE
from model.menu import Menu
from model.submenu import SubMenu
from model.repo_utils import run

from model.utils import walklevel

from pathlib import Path

class AddMenu(SubMenu):
    __slots__ = ['repo_paths', 'read_files', 'config', 'repos_folder_path', 'repos_previous_commit_hash']

    def __init__(self, config):
        self.config = config
        self.repo_paths = []
        self.repos_previous_commit_hash = []
        self.read_files = asyncio.Queue()

        self.repos_folder_path = input('Enter path to cloned repos: ')
        while not Path(self.repos_folder_path).exists():
            self.repos_folder_path = input(f'{LIGHT_RED}Path entered does not exist{WHITE}\nEnter path to cloned repos: ')

        for root, folders, files in walklevel(self.repos_folder_path):
            if '.git' in folders:
                self.repo_paths.append(root)

        loop1 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop1)
        loop1.run_until_complete(self.read_files_to_mem())

        loop2 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop2)
        loop2.run_until_complete(self.write_to_repos())

        loop1 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop1)
        loop1.run_until_complete(self.do_all_git_workflow())

        print(f'{LIGHT_GREEN}Done.{WHITE}')


    async def read_file_to_mem(self, file_path):
        content = None
        if not Path(file_path).is_dir():
            content = Path(file_path).read_bytes()
        await self.read_files.put([file_path, content])
        return True


    async def read_files_to_mem(self):
        tasks = []
        for root, folders, files in os.walk('./data/files_to_add/'): # self.config.files_to_add_path
            for file in folders + files:
                if '.git' in file:
                    continue

                task = asyncio.ensure_future(self.read_file_to_mem(str(Path(root) / Path(file))))
                tasks.append(task)
        await asyncio.gather(*tasks)


    async def write_file(self, info, repo_path):
        path = info[0][len('./data/files_to_add/') - 2:] # self.config.files_to_add_path
        content = info[1]
        final_path = str(Path(repo_path) / Path(path))
        if content is None:
            try:
                os.mkdir(final_path)
            except FileExistsError:
                pass
        elif final_path.endswith('.zip'):
            shutil.copyfile(info[0], final_path)
        else:
            with open(final_path, 'w') as f:
                f.write(content.decode())


    async def write_to_repos(self):
        tasks = []
        print(f'\nRepos Director: {self.repos_folder_path}')
        while not self.read_files.empty():
            info = await self.read_files.get()
            print(f'    > Writing: {info[0][len("./data/files_to_add/") - 2:]}')
            for repo_path in self.repo_paths:
                task = asyncio.ensure_future(self.write_file(info, repo_path))
                tasks.append(task)
        await asyncio.gather(*tasks)


    async def do_git_workflow(self, repo_path, commit_message):
        await run('git add *', repo_path)
        await run(f'git commit -m "{commit_message}"', repo_path)
        await run('git push', repo_path)


    async def do_all_git_workflow(self):
        tasks = []
        commit_message = 'Add Files Via GCIS Grading Scripts.'
        for repo_path in self.repo_paths:
            print(f'    > Pushing: {repo_path}')
            task = asyncio.ensure_future(self.do_git_workflow(repo_path, commit_message))
            tasks.append(task)
        await asyncio.gather(*tasks)




# async def rollback_all_repos(cloned_repos, date_due, time_due):
#     tasks = []
#     while not cloned_repos.empty():
#         repo = await cloned_repos.get()
#         commit_hash = await repo.get_commit_hash(date_due, time_due)

#         if not commit_hash:
#             print(f'    > {LIGHT_RED}Get Commit Hash Failed: [{repo.old_name()}] {repo} likely accepted assignment after given date/time.{WHITE}')
#             await log_info('Get Commit Hash Failed', 'Likely accepted assignment after given date/time.', repo)
#             await repo.delete()
#             continue

#         task = asyncio.ensure_future(repo.rollback(commit_hash))
#         tasks.append(task)
#     await asyncio.gather(*tasks)


# async def clone_repo(repo, path, filename, token, cloned_repos):
#     # If no commits, skip repo
#     destination_path = f'{path}/{filename}'
#     print(f'    > Cloning [{repo.name}] {filename}...') # tell end user what repo is being cloned and where it is going to
#     # run process on system that executes 'git clone' command. stdout is redirected so it doesn't output to end user
#     clone_url = repo.clone_url.replace('https://', f'https://{token}@')
#     cmd = f'git clone --single-branch {clone_url} "{destination_path}"'
#     await run(cmd)
#     local_repo = LocalRepo(destination_path, repo.name, filename, repo)
#     await cloned_repos.put(local_repo)
#     return True


# async def clone_all_repos(repos, path, students, assignment_name, token, cloned_repos):
#     tasks = []
#     for repo in repos:
#         task = asyncio.ensure_future(clone_repo(repo, path, get_new_repo_name(repo, students, assignment_name), token, cloned_repos))
#         tasks.append(task)
#     await asyncio.gather(*tasks)
