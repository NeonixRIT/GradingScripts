# add/edit/delete clone presets
import copy
import model
import os

from pathlib import Path

from model.colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE

PROMPT_INDEX_TEXT = {
    0: 'Enter new preset name: ',
    1: 'Enter new preset file suffix: ',
    2: 'Enter new preset clone time: ',
    3: 'Enter new preset students csv path: ',
    4: f'Would you like to append timestamp to the file suffix ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? '
}

class EditPresetMenu(model.SubMenu):
    __slots__ = ['config', 'local_options', 'preset_index', 'preset']

    def __init__(self, config, preset_name):
        self.config = config
        self.local_options = []
        self.preset_index, self.preset = self.find_preset_by_name(preset_name)

        edit_name_event = model.Event()
        edit_name_event += lambda: self.edit_config_value(0)
        edit_name = model.MenuOption(1, f'Name: {self.preset[0]}', edit_name_event, False)
        self.local_options.append(edit_name)

        edit_suffix_event = model.Event()
        edit_suffix_event += lambda: self.edit_config_value(1)
        edit_suffix = model.MenuOption(2, f'File Suffix: {self.preset[1]}', edit_suffix_event, False)
        self.local_options.append(edit_suffix)

        edit_time_event = model.Event()
        edit_time_event += lambda: self.edit_config_value(2)
        edit_time = model.MenuOption(3, f'Clone Time: {self.preset[2]}', edit_time_event, False)
        self.local_options.append(edit_time)

        edit_csv_event = model.Event()
        edit_csv_event += lambda: self.edit_config_value(3)
        edit_csv = model.MenuOption(4, f'Students CSV: {self.preset[3]}', edit_csv_event, False)
        self.local_options.append(edit_csv)

        edit_app_time_event = model.Event()
        edit_app_time_event += lambda: self.edit_config_value(4)
        edit_app_time = model.MenuOption(4, f'Append Time: {self.preset[4]}', edit_app_time_event, False)
        self.local_options.append(edit_app_time)

        def update_options():
            self.preset = self.config.presets[self.preset_index]
            edit_name.text = self.preset[0]
            edit_suffix.text = self.preset[1]
            edit_time.text = self.preset[2]
            edit_csv.text = self.preset[3]

        delete_preset_event = model.Event()
        delete_preset_event += self.delete_preset
        delete_preset = model.MenuOption(5, "Delete Preset", delete_preset_event, False)
        self.local_options.append(delete_preset)

        edit_name.on_select += update_options
        edit_suffix.on_select += update_options
        edit_time.on_select += update_options
        edit_csv.on_select += update_options

        model.SubMenu.__init__(self, f'Manage Preset: {CYAN}{preset_name}{WHITE}', self.local_options)


    def run(self):
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            handle_option_return = self.handle_option(user_input)
            if user_input.lower() == '5':
                break
        model.utils.clear()


    def delete_preset(self):
        del(self.config.presets[self.preset_index])
        model.utils.save_config(self.config)
        self.config = model.utils.read_config('./data/config.json')


    def edit_config_value(self, value_index: int):
        prompt = PROMPT_INDEX_TEXT[value_index]
        new_value = input(prompt)
        if value_index == 0:
            while model.utils.check_preset_names(self.config, new_value):
                new_value = input(f'{LIGHT_RED}That name already exists{WHITE}\n{prompt}')
        if value_index == 1:
            pass # check that doesnt contain invalid file character
        if value_index == 2:
            while not model.repo_utils.check_time(new_value):
                new_value = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37){WHITE}\n{prompt}')
        if value_index == 3:
            while not Path(new_value).exists() or not new_value.endswith('.csv'):
                new_value = input(f'{LIGHT_RED}No Students CSV found at: {new_value}{WHITE}\n{prompt}')
        if value_index == 4:
            new_value = True if new_value == 'y' or new_value == 'yes' else False

        self.set_config_value(value_index, new_value)


    def set_config_value(self, value_index, new_value):
        model.utils.clear()
        self.preset[value_index] = new_value
        self.config.presets[self.preset_index] = self.preset
        model.utils.save_config(self.config)
        self.config = model.utils.read_config('./data/config.json')
        model.utils.clear()


    def create_preset(self):
        prompt_prefix = 'Enter this preset\'s'
        name = input(f'{prompt_prefix} name: ')
        folder_suffix = input(f'{prompt_prefix} folder suffix: ')
        clone_time = input(f'{prompt_prefix} clone time: ')
        while not model.repo_utils.check_time(clone_time):
            clone_time = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37)\n{prompt_prefix} clone time: ')
        csv_path = input(f'{prompt_prefix} desired csv file (enter for default): ')
        append_timestamp = input(f'Would you like to append a timestamp to the folder suffix ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? ').lower()

        append_timestamp = True if append_timestamp == 'y' or append_timestamp == 'yes' else False
        if not csv_path:
            csv_path = self.config.students_csv

        self.config.presets.append([name, folder_suffix, clone_time, csv_path, append_timestamp])
        model.utils.save_config(self.config)


    def find_preset_by_name(self, name) -> tuple:
        for i, preset in enumerate(self.config.presets):
            if preset[0] == name:
                return i, preset
