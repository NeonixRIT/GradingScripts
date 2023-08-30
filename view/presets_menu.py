from .edit_preset_menu import EditPresetMenu

from tuiframeworkpy import SubMenu, Event, MenuOption, LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from utils import bool_prompt, list_to_multi_clone_presets, check_time

class PresetsMenu(SubMenu):
    __slots__ = ['config', 'preset_options', 'local_options']

    def __init__(self, id):
        self.local_options = []
        self.preset_options = []

        add_preset_event = Event()
        add_preset_event += self.create_preset
        add_preset = MenuOption(1, "Create New Preset", add_preset_event, Event(), Event())
        add_preset.on_exit += self.load
        self.local_options.append(add_preset)

        SubMenu.__init__(self, id, 'Manage Presets', self.preset_options + self.local_options, Event(), Event())

    def load(self):
        self.preset_options = self.build_preset_options()
        for i, option in enumerate(self.local_options):
            option.number = len(self.preset_options) + i + 1
        options = self.preset_options + self.local_options
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.prompt_string = self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'

    def build_preset_options(self):
        options = []
        for i, preset in enumerate(list_to_multi_clone_presets(self.context.config_manager.config.presets)):
            option_event = Event()

            def on_select(bound_preset=preset):
                EditPresetMenu(self.context, 12, bound_preset.name).run()

            option_event += on_select
            option = MenuOption(i + 1, preset.name, option_event, Event(), Event(), False)
            option.on_exit += self.load
            options.append(option)
        return options

    def create_preset(self):
        prompt_prefix = 'Enter this preset\'s'
        name = input(f'{prompt_prefix} name: ')
        while self.check_preset_names(name):
            name = input(f'That name already exists\n{prompt_prefix} name: ')

        folder_suffix = input(f'{prompt_prefix} folder suffix: ')
        clone_time = input(f'{prompt_prefix} clone time: ')
        while not check_time(clone_time):
            clone_time = input(f'{LIGHT_RED}Time was in an invalid format. Use 24 hour time (e.g. 13:37){WHITE}\n{prompt_prefix} clone time: ')
        csv_path = input(f'{prompt_prefix} desired csv file (enter for default): ')
        append_timestamp = bool_prompt('Would you like to append timestamp to the folder name?', False)

        clone_type_flag = (0, 0, 0)
        res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ')
        while res != 'ca' and res != 'as' and res != 'ex':
            res = input(f'Is this for a {LIGHT_GREEN}class activity(ca){WHITE}, {LIGHT_GREEN}assignment(as){WHITE}, or {LIGHT_GREEN}exam(ex){WHITE}? ')
        if res == 'ca':
            clone_type_flag = (1, 0, 0)
        elif res == 'as':
            clone_type_flag = (0, 1, 0)
        elif res == 'ex':
            clone_type_flag = (0, 0, 1)

        if not csv_path:
            csv_path = self.context.config_manager.config.students_csv

        self.context.config_manager.config.presets.append([name, folder_suffix, clone_time, csv_path, append_timestamp, clone_type_flag])
        self.context.config_manager.save_config()

    def check_preset_names(self, name):
        for preset in list_to_multi_clone_presets(self.context.config_manager.config.presets):
            if preset.name == name:
                return True
        return False
