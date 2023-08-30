from typing import Any

from tuiframeworkpy import Event, MenuOption, SubMenu, LIGHT_GREEN, LIGHT_RED, WHITE
from utils import clear, bool_prompt, get_color_from_bool, censor_string


class ConfigMenu(SubMenu):
    __slots__ = ['custom_edit_fields']

    def __init__(self, id: int, custom_edit_fields: dict[str, Any] = None):
        if custom_edit_fields is not None:
            self.custom_edit_fields = custom_edit_fields
        else:
            self.custom_edit_fields = dict()
        SubMenu.__init__(self, id, 'Change Config Values', [], Event(), Event())

    def load(self):
        self.options = {}
        for i, entry in enumerate(self.context.config_manager.config_entries):
            if not entry.prompt:
                continue
            value = getattr(self.context.config_manager.config, entry.name)
            if entry.censor:
                value = censor_string(value)
            on_select = Event()
            on_select += lambda value_name=entry.name: self.edit_config_value(value_name)
            if entry.name == 'metrics_api':
                on_select += self.context.main.update_metrics_client
            if isinstance(value, type(list())):
                text = f'{entry.friendly_name}'
            else:
                text = f'{entry.friendly_name}: {get_color_from_bool(value)}{value}{WHITE}' if entry.is_bool_prompt else f'{entry.friendly_name}: {value}'
            option = MenuOption(i + 1, text, on_select, Event(), Event(), pause=False)
            option.on_select += self.load
            self.options[option.number] = option

        self.min_options = 1
        self.max_options = max(self.options.keys())
        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to enter the value manually: '
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'

    def edit_config_value(self, value_name: str):
        clear()
        entry = self.context.config_manager.name_to_entry[value_name]

        def prompt_func():
            return input(entry.prompt_text) if not entry.is_bool_prompt else bool_prompt(entry.prompt_text, entry.default_value)

        if value_name in self.custom_edit_fields:
            self.custom_edit_fields[value_name](self.context, entry, prompt_func)
            return

        if entry.is_bool_prompt:
            self.set_config_value(value_name, not getattr(self.context.config_manager.config, value_name, True))
        else:
            self.set_config_value(value_name, prompt_func())

    def set_config_value(self, value_name, new_value):
        clear()
        self.context.config_manager.set_config_value(value_name, new_value)
        self.context.config_manager.save_config()
        self.context.config_manager.read_config()
        clear()
