import asyncio
import shutil
import os

from .clone_preset import ClonePreset
from .source_api_client import main

from utils import get_color_from_bool, async_run_cmd, list_to_multi_clone_presets, onerror
from tuiframeworkpy import SubMenu, Event, MenuOption
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, WHITE

# Get computer's current UTC offset
# Then get the inverse so that when due date/time is input in local time, it will be processed as UTC
LOG_FILE_PATH = './data/logs.log'


class CloneMenu(SubMenu):
    __slots__ = ['client', 'local_options', 'preset_options', 'dry_run', 'parameters']

    def __init__(self, id):
        self.client = None
        self.local_options = []
        self.preset_options = []
        self.dry_run = False

        self.parameters = dict()

        manage_presets = MenuOption(1, 'Manage Presets', Event(), Event(), Event(), pause=False)
        manage_presets.on_exit += self.load
        self.local_options.append(manage_presets)

        toggle_dry_run_event = Event()
        toggle_dry_run_event += self.toggle_dry_run
        toggle_dry_run_event += self.load
        toggle_clone_tag = MenuOption(
            2,
            f'Dry Run: {get_color_from_bool(self.dry_run)}{self.dry_run}{WHITE}',
            toggle_dry_run_event,
            Event(),
            Event(),
            pause=False,
        )
        self.local_options.append(toggle_clone_tag)

        clone_history = MenuOption(3, 'Clone History', Event(), Event(), Event(), pause=False)
        clone_history.on_exit += self.load
        self.local_options.append(clone_history)

        clone_repos_event = Event()
        clone_repos_event += self.clone_repos
        clone_repos = MenuOption(4, 'Continue Without Preset', clone_repos_event, Event(), Event())
        self.local_options.append(clone_repos)

        SubMenu.__init__(
            self,
            id,
            'Clone Presets',
            self.preset_options + self.local_options,
            Event(),
            Event(),
            preload=False,
        )
        self.on_enter += self.load

    def load(self):
        self.client = self.parent.client

        self.preset_options = self.build_preset_options()
        for i, option in enumerate(self.local_options):
            option.number = len(self.preset_options) + i + 1
            if option.text.startswith('Dry Run: '):
                option.text = f'Dry Run: {get_color_from_bool(self.dry_run)}{self.dry_run}{WHITE}'
        options = self.preset_options + self.local_options
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'
        self.prompt_string = self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '

    def toggle_dry_run(self):
        self.dry_run = not self.dry_run

    def save_report(self, report):
        clone_logs = self.context.config_manager.config.clone_history
        clone_logs.append(report)
        if len(clone_logs) > 8:
            clone_logs = clone_logs[1:]
        self.context.config_manager.set_config_value('clone_history', clone_logs)

    def clone_repos(self, preset: ClonePreset = None):
        dry_run = bool(self.dry_run)
        main(preset, dry_run, self.context.config_manager)


    def build_preset_options(self) -> list:
        options = []
        for i, preset in enumerate(list_to_multi_clone_presets(self.context.config_manager.config.presets)):
            option_event = Event()

            def on_select(bound_preset=preset):
                self.clone_repos(bound_preset)

            option_event += on_select
            option = MenuOption(i + 1, preset.name, option_event, Event(), Event())
            options.append(option)
        return options
