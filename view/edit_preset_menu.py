from pathlib import Path

from tuiframeworkpy import SubMenu, Event, MenuOption, LIGHT_GREEN, LIGHT_RED, CYAN, WHITE, clear
from utils import list_to_multi_clone_presets, check_time, bool_prompt

# TODO: maybe extract run method and config entry view menu into class for TUIFrameworkPy

PROMPT_INDEX_TEXT = {
    0: 'Enter new preset name: ',
    1: 'Enter new preset file suffix: ',
    2: 'Enter new preset clone time: ',
    3: 'Enter new preset students csv path: ',
    4: 'Would you like to append timestamp to the file suffix?'
}

class EditPresetMenu(SubMenu):
    __slots__ = ['local_options', 'preset_index', 'preset']

    def __init__(self, context, id, preset_name):
        self.context = context
        self.local_options = []
        self.preset_index, self.preset = self.find_preset_by_name(preset_name)

        edit_name_event = Event()
        edit_name_event += lambda: self.edit_config_value(0)
        edit_name = MenuOption(1, f'Name: {self.preset[0]}', edit_name_event, Event(), Event(), False)
        self.local_options.append(edit_name)

        edit_suffix_event = Event()
        edit_suffix_event += lambda: self.edit_config_value(1)
        edit_suffix = MenuOption(2, f'File Suffix: {self.preset[1]}', edit_suffix_event, Event(), Event(), False)
        self.local_options.append(edit_suffix)

        edit_time_event = Event()
        edit_time_event += lambda: self.edit_config_value(2)
        edit_time = MenuOption(3, f'Clone Time: {self.preset[2]}', edit_time_event, Event(), Event(), False)
        self.local_options.append(edit_time)

        edit_csv_event = Event()
        edit_csv_event += lambda: self.edit_config_value(3)
        edit_csv = MenuOption(4, f'Students CSV: {self.preset[3]}', edit_csv_event, Event(), Event(), False)
        self.local_options.append(edit_csv)

        edit_app_time_event = Event()
        edit_app_time_event += lambda: self.edit_config_value(4)
        edit_app_time = MenuOption(5, f'Append Time: {self.preset[4]}', edit_app_time_event, Event(), Event(), False)
        self.local_options.append(edit_app_time)

        delete_preset_event = Event()
        delete_preset_event += self.delete_preset
        delete_preset = MenuOption(6, "Delete Preset", delete_preset_event, Event(), Event(), False)
        self.local_options.append(delete_preset)

        edit_name.on_exit += self.load
        edit_suffix.on_exit += self.load
        edit_time.on_exit += self.load
        edit_csv.on_exit += self.load
        edit_app_time.on_exit += self.load

        SubMenu.__init__(self, id, f'Manage Preset: {CYAN}{preset_name}{WHITE}', self.local_options)


    def load(self):
        self.preset = self.context.config_manager.config.presets[self.preset_index]

        for num, option in self.options.items():
            i = num - 1
            if option.text.startswith('Name'):
                option.text = f'Name: {self.preset[i]}'
            elif option.text.startswith('File Suffix'):
                option.text = f'File Suffix: {self.preset[i]}'
            elif option.text.startswith('Clone Time'):
                option.text = f'Clone Time: {self.preset[i]}'
            elif option.text.startswith('Students CSV'):
                option.text = f'Students CSV: {self.preset[i]}'
            elif option.text.startswith('Append Time'):
                option.text = f'Append Time: {self.preset[i]}'


    def run(self):
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            handle_option_return = self.handle_option(user_input)
            if user_input.lower() == '6':
                break
        clear()


    def delete_preset(self):
        del self.context.config_manager.config.presets[self.preset_index]
        self.context.config_manager.save_config()
        self.context.config_manager.read_config()


    def edit_config_value(self, value_index: int):
        prompt = PROMPT_INDEX_TEXT[value_index]
        if value_index == 4:
            new_value = bool_prompt(prompt, False)
        else:
            new_value = input(prompt)

        if value_index == 0:
            while self.check_preset_names(new_value):
                new_value = input(f'{LIGHT_RED}That name already exists{WHITE}\n{prompt}')
        if value_index == 1:
            pass # check that doesnt contain invalid file character
        if value_index == 2:
            while not check_time(new_value):
                new_value = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37){WHITE}\n{prompt}')
        if value_index == 3:
            while not Path(new_value).exists() or not new_value.endswith('.csv'):
                new_value = input(f'{LIGHT_RED}No Students CSV found at: {new_value}{WHITE}\n{prompt}')

        self.set_config_value(value_index, new_value)


    def set_config_value(self, value_index, new_value):
        clear()
        self.preset[value_index] = new_value
        self.context.config_manager.config.presets[self.preset_index] = self.preset
        self.context.config_manager.save_config()
        self.context.config_manager.read_config()
        clear()


    def create_preset(self):
        prompt_prefix = 'Enter this preset\'s'
        name = input(f'{prompt_prefix} name: ')
        folder_suffix = input(f'{prompt_prefix} folder suffix: ')
        clone_time = input(f'{prompt_prefix} clone time: ')
        while not check_time(clone_time):
            clone_time = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37)\n{prompt_prefix} clone time: ')
        csv_path = input(f'{prompt_prefix} desired csv file (enter for default): ')
        append_timestamp = input(f'Would you like to append a timestamp to the folder suffix ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? ').lower()

        append_timestamp = True if append_timestamp == 'y' or append_timestamp == 'yes' else False
        if not csv_path:
            csv_path = self.context.config_manager.config.students_csv

        self.context.config_manager.config.presets.append([name, folder_suffix, clone_time, csv_path, append_timestamp])
        self.context.config_manager.save_config()


    def find_preset_by_name(self, name) -> tuple:
        for i, preset in enumerate(self.context.config_manager.config.presets):
            if preset[0] == name:
                return i, preset


    def check_preset_names(self, name):
        for preset in list_to_multi_clone_presets(self.context.config_manager.config.presets):
            if preset.name == name:
                return True
        return False
