import asyncio
import logging
import model
import os
import threading

from .presets_menu import PresetsMenu

from pathlib import Path
from types import SimpleNamespace

LOG_FILE_PATH = './data/logs.log'

class ReposStruct:
    __slots__ = ['repos_w_students']

    def __init__(self):
        pass


class CloneMenu(model.SubMenu):
    __slots__ = ['config', 'students', 'client', 'repos', 'cloned_repos', 'no_commits_tuples', 'no_commits_students', 'local_options', 'preset_options', 'clone_via_tag']

    def __init__(self, config, client, repos, students):
        self.config = config
        self.client = client
        self.repos = repos
        self.students = students
        self.cloned_repos = None # async queue
        self.no_commits_tuples = set()
        self.no_commits_students = set()
        self.local_options = []
        self.preset_options = []
        self.clone_via_tag = False

        # whenever add/delete preset, update options list
        self.preset_options = self.build_preset_options()

        manage_presets_event = model.Event()
        manage_presets_event += PresetsMenu(self.config).run
        manage_presets = model.MenuOption(len(self.config.presets) + 1, 'Manage Presets', manage_presets_event, False)
        self.local_options.append(manage_presets)

        toggle_clone_tag_event = model.Event()

        def toggleCloneViaTag():
            self.clone_via_tag = not self.clone_via_tag

        toggle_clone_tag_event += toggleCloneViaTag
        toggle_clone_tag = model.MenuOption(len(self.config.presets) + 2, f'Clone Via Tag: {model.utils.get_color_from_bool(self.clone_via_tag)}{self.clone_via_tag}{model.colors.WHITE}', toggle_clone_tag_event, False)
        self.local_options.append(toggle_clone_tag)

        clone_repos_event = model.Event()
        clone_repos_event += self.clone_repos
        clone_repos = model.MenuOption(len(self.config.presets) + 3, 'Continue Without Preset', clone_repos_event)
        self.local_options.append(clone_repos)

        def update_options():
            self.config = model.utils.read_config('./data/config.json')
            self.preset_options = self.build_preset_options()
            for i, option in enumerate(self.local_options):
                option.number = len(self.preset_options) + i + 1
                if option.text.startswith('Clone Via Tag: '):
                    option.text = f'Clone Via Tag: {model.utils.get_color_from_bool(self.clone_via_tag)}{self.clone_via_tag}{model.colors.WHITE}'
            options = self.preset_options + self.local_options
            self.options = dict()
            for menu_option in options:
                self.options[menu_option.number] = menu_option

        manage_presets_event += update_options
        toggle_clone_tag_event += update_options

        model.SubMenu.__init__(self, 'Clone Presets', self.preset_options + self.local_options)


    def clone_repos(self, preset: model.clone_preset.ClonePreset = None):
        students_path = self.config.students_csv
        if preset is not None:
            students_path = preset.csv_path
            self.students = model.repo_utils.get_students(students_path)
        else:
            preset = model.clone_preset.ClonePreset('', '', '', students_path, False)
            append_timestamp_input = input(f'Append timestamp to repo folder name?\nIf using a tag name, it will append the tag instead ({model.colors.LIGHT_GREEN}Y{model.colors.WHITE}/{model.colors.LIGHT_RED}N{model.colors.WHITE}). ').lower()
            preset.append_timestamp = False if append_timestamp_input == 'n' or append_timestamp_input == 'no' else True

        assignment_name = model.repo_utils.attempt_get_assignment() # prompt assignment name
        assignment_name, self.repos = model.utils.verify_assignment_name(assignment_name, self.repos)

        due_tag = ''
        if self.clone_via_tag:
            due_tag = model.repo_utils.attempt_get_tag()

            if preset.append_timestamp:
                preset.folder_suffix += f'_{due_tag}'

        repos_struct = ReposStruct()
        thread = threading.Thread(target=lambda: self.get_repos_specified_students(self.repos, assignment_name, due_tag, repos_struct))
        thread.start()

        due_date = ''
        if not self.clone_via_tag:
            preset.clone_time = model.repo_utils.get_time()

            due_date = model.repo_utils.get_date()
            while not model.repo_utils.check_date(due_date):
                due_date = model.repo_utils.get_date()

            if preset.append_timestamp:
                date_str = due_date[4:].replace('-', '_')
                time_str = preset.clone_time.replace(':', '_')
                preset.folder_suffix += f'_{date_str}_{time_str}'

        parent_folder_path = f'{self.config.out_dir}/{assignment_name}{preset.folder_suffix}' # prompt parent folder (IE assingment_name-AS in config.out_dir)

        i = 0
        while Path(parent_folder_path).exists():
            i += 1
            parent_folder_path = f'{self.config.out_dir}/{assignment_name}{preset.folder_suffix}_iter_{i}'

        os.mkdir(parent_folder_path)
        thread.join()
        self.repos = repos_struct.repos_w_students
        if len(self.repos) == 0:
            print(f'{model.colors.LIGHT_RED}No repos found for specified students.{model.colors.WHITE}')
            return

        print()
        print(f'Output directory: {parent_folder_path[len(self.config.out_dir) + 1:]}')

        for repo_info in self.no_commits_tuples:
            repo_name = repo_info[0]
            repo_new = repo_info[1]
            text = f'    > {model.colors.LIGHT_RED}Skipping because [{repo_name}] {repo_new} does not have the tag.{model.colors.WHITE}' if self.clone_via_tag else f'    > {model.colors.LIGHT_RED}Skipping because [{repo_name}] {repo_new} does not have any commits.{model.colors.WHITE}'
            print(text)

        not_accepted = set()
        not_accepted = model.repo_utils.find_students_not_accepted(self.students, self.repos, assignment_name, self.no_commits_students, due_tag)
        for student in not_accepted:
            not_accepted_text = f'    > {model.colors.LIGHT_RED}Skipping because [{student}] {self.students[student]} did not accept the assignment.{model.colors.WHITE}'
            print(not_accepted_text)

        cloned_repos = asyncio.Queue()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(model.repo_utils.clone_all_repos(self.repos, parent_folder_path, self.students, assignment_name, self.config.token, due_tag, cloned_repos))

        if not self.clone_via_tag:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(model.repo_utils.rollback_all_repos(cloned_repos, due_date, preset.clone_time))
        else:
            del cloned_repos

        model.repo_utils.print_end_report(self.students, self.repos, len(not_accepted), len(os.listdir(parent_folder_path)), self.no_commits_students)
        model.repo_utils.extract_data_folder(parent_folder_path)

    def build_preset_options(self) -> list:
        options = []
        for i, preset in enumerate(model.utils.list_to_multi_clone_presets(self.config.presets)):
            option_event = model.event.Event()

            def on_select(bound_preset=preset):
                self.clone_repos(bound_preset)

            option_event += on_select
            option = model.menu_option.MenuOption(i + 1, preset.name, option_event)
            options.append(option)
        return options


    def is_valid_repo(self, repo, assignment_name: str, due_tag: str) -> bool:
        is_student_repo = repo.name.replace(f'{assignment_name}-', '') in self.students
        has_tag = (repo.get_tags().totalCount > 0 and due_tag in [tag.name for tag in repo.get_tags()])
        if is_student_repo and len(list(repo.get_commits())) - 1 <= 0:
            self.no_commits_tuples.add((repo.name, model.repo_utils.get_new_repo_name(repo, self.students, assignment_name)))
            self.no_commits_students.add(repo.name.replace(f'{assignment_name}-', ''))
            return False
        elif is_student_repo and not has_tag:
            self.no_commits_tuples.add((repo.name, model.repo_utils.get_new_repo_name(repo, self.students, assignment_name)))
            self.no_commits_students.add(repo.name.replace(f'{assignment_name}-', ''))
            return False
        return is_student_repo


    def get_repos_specified_students(self, assignment_repos, assignment_name: str, due_tag: str, repos_struct):
        '''
        return list of all repos in an organization matching assignment name prefix and is a student specified in the specified class roster csv
        '''
        repos_struct.repos_w_students = set(filter(lambda repo: self.is_valid_repo(repo, assignment_name, due_tag), assignment_repos))
