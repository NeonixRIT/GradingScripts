import json
import os

from .config_entry import ConfigEntry
from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .event import Event
from .enhanced_json_decoder import EnhancedJSONEncoder

from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any, Iterable


class ConfigManager:
    __slots__ = [
        'config_path',
        'config',
        'config_entries',
        'path_entries',
        'censored_entries',
        'default_config_dict',
        'friendly_names_dict',
        'name_to_entry',
        'custom_verify_methods',
        'on_config_change',
        'on_config_save',
        'on_config_read',
        'on_config_verify',
        'depends_loaded',
    ]

    def __init__(self, config_path: str, config_entries: list[ConfigEntry] = None):
        if config_entries is None:
            config_entries = []
        self.config_path = config_path
        self.config_entries = config_entries

        self.on_config_change = Event()
        self.on_config_save = Event()
        self.on_config_read = Event()
        self.on_config_verify = Event()

        self.config = None
        self.custom_verify_methods = Event()

        self.path_entries = []
        self.censored_entries = []
        self.default_config_dict = {}
        self.friendly_names_dict = {}
        self.name_to_entry = {}
        for entry in self.config_entries:
            if entry.is_path:
                self.path_entries.append(entry.name)
            if entry.censor:
                self.censored_entries.append(entry.name)
            if entry.is_bool_prompt and not isinstance(entry.default_value, bool):
                raise TypeError('ConfigEntry default_value must be a bool if bool_prompt is true.')
            self.friendly_names_dict[entry.name] = entry.friendly_name
            self.default_config_dict[entry.name] = entry.default_value
            self.name_to_entry[entry.name] = entry
        self.depends_loaded = False

    def __str__(self) -> str:
        result = ''
        for key, value in self.config.__dict__.items():
            if key in self.censored_entries:
                result += f'    {self.friendly_names_dict[key]}: {self.__censor_string(value)}\n'
            else:
                result += f'    {self.friendly_names_dict[key]}: {value}\n'
        return result

    def __iadd__(self, other: ConfigEntry | list[ConfigEntry] | Any):
        if isinstance(other, ConfigEntry) or (isinstance(other, list) and len(other) > 0 and isinstance(other[0], ConfigEntry)):
            self.config_entries.append(other)
        elif callable(other):
            self.custom_verify_methods += lambda: other(self.config)
        return self

    def initialize(self):
        if not Path(self.config_path).exists():
            self.make_new_config()
            self.save_config()
        else:
            self.read_config()

    def __verify_on_depends_loaded(self):
        from time import sleep

        while True:
            if self.depends_loaded:
                self.verify_config()
                break
            sleep(0.5)

    def read_config(self) -> SimpleNamespace:
        config = json.loads(
            Path(self.config_path).read_text(),
            object_hook=lambda d: SimpleNamespace(**d),
        )
        self.config = config
        if self.depends_loaded:
            self.verify_config()
        else:
            Thread(target=self.__verify_on_depends_loaded).start()

    def save_config(self):
        self.verify_config()
        config_str = json.dumps(self.config.__dict__, indent=4, cls=EnhancedJSONEncoder)
        dirs = self.config_path.split('/')

        path = ''
        for dir in dirs[:-1]:
            path += dir + '/'
            if not Path(path).exists():
                os.mkdir(dir)

        with open(self.config_path, 'w') as f:
            f.write(config_str)
            f.flush()

    def make_new_config(self):
        print(f'{CYAN}Welcome to the initial setup.{WHITE}')
        print(f'{CYAN}We will be creating a new config file at {self.config_path}{WHITE}')
        print(f'{CYAN}There are just a few values you need to enter first.{WHITE}\n')
        values = {}
        for entry in self.config_entries:
            if not entry.prompt:
                values[entry.name] = entry.default_value
                continue
            entry_value = ''
            if entry.is_bool_prompt:
                entry_value = self.bool_prompt(entry.prompt_text, entry.default_value)
            else:
                entry_value = input(entry.prompt_text)

            if not entry_value and isinstance(entry_value, str):
                entry_value = entry.default_value

            values[entry.name] = entry_value

        values_formatted = json.dumps(values, indent=4, cls=EnhancedJSONEncoder)
        self.config = json.loads(values_formatted, object_hook=lambda d: SimpleNamespace(**d))
        self.verify_config()

    def verify_paths(self) -> set:
        invalid_fields = set()
        for path_entry in self.path_entries:
            value = getattr(self.config, path_entry, None)
            if not value or not Path(value).exists():
                invalid_fields.add(path_entry)
        return invalid_fields

    def verify_config(self):
        if not self.depends_loaded:
            return

        missing_fields = set()
        for entry in self.config_entries:
            if getattr(self.config, entry.name, None) is None:
                if entry.prompt and (entry.default_value is None or entry.is_bool_prompt):
                    missing_fields.add(entry.name)
                else:
                    setattr(self.config, entry.name, entry.default_value)

        invalid_fields = {value for value in self.verify_paths() or missing_fields or self.__flatten_set(self.custom_verify_methods())}
        if len(invalid_fields) > 0:
            print(f'{LIGHT_RED}WARNING: Some values in your config seem to be missing or invalid. Please enter their fixed values.{WHITE}')
        for field in invalid_fields:
            entry = self.name_to_entry[field]

            def prompt_func(bound_entry=entry):
                if bound_entry.is_bool_prompt:
                    return self.bool_prompt(bound_entry.prompt_text, bound_entry.default_value)
                else:
                    return input(bound_entry.prompt_text)

            new_value = prompt_func()
            setattr(self.config, field, new_value)

        if len(invalid_fields) > 0:
            self.save_config()

    def bool_prompt(self, prompt: str, default_output: bool) -> bool:
        y_str = 'Y' if default_output else 'y'
        n_str = 'N' if not default_output else 'n'
        result = input(f'{prompt} ({LIGHT_GREEN}{y_str}{WHITE}/{LIGHT_RED}{n_str}{WHITE}): ')
        return default_output if not result else True if result.lower() == 'y' else False if result.lower() == 'n' else default_output

    def set_config_value(self, name: str, value: Any):
        setattr(self.config, name, value)
        self.save_config()

    def __censor_string(self, string: str) -> str | None:
        if len(string) <= 7:
            return
        return ('*' * int(len(string) - len(string) / 5)) + string[-int(len(string) / 5) :]

    def __flatten_set(self, iter: Iterable):
        return {item for sublist in iter for item in sublist}
