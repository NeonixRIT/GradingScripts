import model
import os

from model.colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .edit_preset_menu import EditPresetMenu

class PresetsMenu(model.SubMenu):
    __slots__ = ['config', 'preset_options', 'local_options']

    def __init__(self, config):
        self.config = config
        self.preset_options = self.build_preset_options()
        self.local_options = []

        add_preset_event = model.Event()
        add_preset_event += self.create_preset
        add_preset = model.MenuOption(len(self.preset_options) + 1, "Create New Preset", add_preset_event)
        self.local_options.append(add_preset)

        def update_options():
            self.config = model.utils.read_config('./data/config.json')
            self.preset_options = self.build_preset_options()
            for i, option in enumerate(self.local_options):
                option.number = len(self.preset_options) + i + 1
            options = self.preset_options + self.local_options
            self.options = dict()
            for menu_option in options:
                self.options[menu_option.number] = menu_option

        add_preset_event += update_options

        model.SubMenu.__init__(self, 'Manage Presets', self.preset_options + self.local_options)


    def build_preset_options(self):
        options = []
        for i, preset in enumerate(model.utils.list_to_multi_clone_presets(self.config.presets)):
            option_event = model.event.Event()

            def on_select(bound_preset=preset):
                EditPresetMenu(self.config, bound_preset.name).run()

            def update_options():
                self.config = model.utils.read_config('./data/config.json')
                self.preset_options = self.build_preset_options()
                for i, option in enumerate(self.local_options):
                    option.number = len(self.preset_options) + i + 1
                options = self.preset_options + self.local_options
                self.options = dict()
                for menu_option in options:
                    self.options[menu_option.number] = menu_option

            option_event += on_select
            option_event += update_options
            option = model.menu_option.MenuOption(i + 1, preset.name, option_event, False)
            options.append(option)
        return options


    def __set_config_value(self, value_name, new_value):
        model.utils.clear()
        setattr(self.config, value_name, new_value)
        model.utils.save_config(self.config)
        self.config = model.utils.read_config('./data/config.json')
        model.utils.clear()


    def create_preset(self):
        prompt_prefix = 'Enter this preset\'s'
        name = input(f'{prompt_prefix} name: ')
        while model.utils.check_preset_names(self.config, name):
            name = input(f'That name already exists\n{prompt_prefix} name: ')

        folder_suffix = input(f'{prompt_prefix} folder suffix: ')
        clone_time = input(f'{prompt_prefix} clone time: ')
        while not model.repo_utils.check_time(clone_time):
            clone_time = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37){WHITE}\n{prompt_prefix} clone time: ')
        csv_path = input(f'{prompt_prefix} desired csv file (enter for default): ')
        append_timestamp = input(f'Would you like to append a timestamp to the folder suffix ({LIGHT_GREEN}Y{WHITE}/{LIGHT_RED}N{WHITE})? ').lower()

        append_timestamp = True if append_timestamp == 'y' or append_timestamp == 'yes' else False
        if not csv_path:
            csv_path = self.config.students_csv

        self.config.presets.append([name, folder_suffix, clone_time, csv_path, append_timestamp])
        model.utils.save_config(self.config)
