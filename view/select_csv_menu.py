import os

from tuiframeworkpy import SubMenu, Event, MenuOption, LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from utils import clear


class SelectCSVMenu(SubMenu):
    __slots__ = ['student_csv_menu_quit']

    def __init__(self, id, context):
        self.student_csv_menu_quit = False
        self.context = context

        separator = '/' if '/' in self.context.config_manager.config.students_csv else '\\'
        current_default = self.context.config_manager.config.students_csv.split(separator)[-1]
        options = []
        for i, file_name in enumerate([f'* {file}' if current_default == file else file for file in os.listdir('./data/csvs/') if file.endswith('.csv')]):
            on_select = Event()

            def set_csv_values(bound_file_name=file_name):
                value = bound_file_name.replace('* ', '')
                self.__set_config_value('students_csv', './data/csvs/' + value)

            on_select += set_csv_values
            menu_option = MenuOption(i + 1, f'{CYAN if file_name.replace("* ", "") == current_default else WHITE}{file_name}{WHITE}', on_select, Event(), Event(), False)
            options.append(menu_option)

        SubMenu.__init__(self, id, 'Select New CSV File', options, Event(), Event(), only_one_prompt=True)
        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to enter the value manually: '
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'

    def __set_config_value(self, value_name, new_value):
        clear()
        self.context.config_manager.set_config_value(value_name, new_value)
        self.context.config_manager.read_config()
        clear()

    def run(self):
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            if user_input.lower() == 'q' or user_input.lower() == 'quit':
                self.student_csv_menu_quit = True
            handle_option_return = self.handle_option(user_input)
        clear()
