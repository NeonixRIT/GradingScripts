import model
import os

class SelectCSVMenu(model.SubMenu):
    __slots__ = ['config', 'student_csv_menu_quit']

    def __init__(self, config):
        self.student_csv_menu_quit = False
        self.config = config

        separator = '/' if '/' in self.config.students_csv else '\\'
        current_default = self.config.students_csv.split(separator)[-1]
        options = []
        for i, file_name in enumerate([f'* {file}' if current_default == file else file for file in os.listdir('./data/csvs/') if file.endswith('.csv')]):
            on_select = model.event.Event()

            def set_csv_values(bound_file_name=file_name):
                value = bound_file_name.replace('* ', '')
                self.__set_config_value('students_csv', './data/csvs/' + value)

            on_select += set_csv_values
            menu_option = model.menu_option.MenuOption(i + 1, f'{model.colors.CYAN if file_name.replace("* ", "") == current_default else model.colors.WHITE}{file_name}{model.colors.WHITE}', on_select, False)
            options.append(menu_option)

        model.SubMenu.__init__(self, 'Select New CSV File', options, True)
        self.prompt_string = f'Please enter a number {model.utils.LIGHT_GREEN}({self.min_options}-{self.max_options}){model.utils.WHITE} or {model.utils.LIGHT_RED}q/quit{model.utils.WHITE} to enter the value manually: '

    def __set_config_value(self, value_name, new_value):
        model.utils.clear()
        setattr(self.config, value_name, new_value)
        model.utils.save_config(self.config)
        self.config = model.utils.read_config('./data/config.json')
        model.utils.clear()


    def __quit(self):
        model.utils.clear()


    def run(self):
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            if user_input.lower() == 'q' or user_input.lower() == 'quit':
                self.student_csv_menu_quit = True
            handle_option_return = self.handle_option(user_input)
        model.utils.clear()
