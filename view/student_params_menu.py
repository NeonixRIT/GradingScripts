from .student_param import StudentParam
from .github_client import get_students

from tuiframeworkpy import SubMenu, Event, MenuOption, LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from utils import clear


def prompt_for_digit(prompt_string: str) -> float:
    value = input(prompt_string)
    while not value.replace('.', '', 1).isdigit():
        value = input('Please enter a floatable number: ')
    return float(value)


class StudentParamsMenu(SubMenu):
    def __init__(self, id, context):
        self.context = context

        self.local_options = []
        self.preset_options = []

        create_params_event = Event()
        create_params_event += self.create_param
        create_params = MenuOption(1, "Create New", create_params_event, Event(), Event())
        create_params.on_exit += self.load
        self.local_options.append(create_params)

        SubMenu.__init__(self, id, 'Student Params', self.preset_options + self.local_options, Event(), Event())

    def load(self):
        self.preset_options = self.build_preset_options()
        for i, option in enumerate(self.local_options):
            option.number = len(self.preset_options) + i + 1
        options = self.preset_options + self.local_options
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'

    def build_preset_options(self):
        options = []
        for i, params in enumerate(self.context.config_manager.config.extra_student_parameters):
            option_event = Event()
            option_event += lambda bound_params=params: self.edit_param(bound_params)
            option = MenuOption(i + 1, params.name, option_event, Event(), Event(), False)
            option.on_exit += self.load
            options.append(option)
        return options

    def create_param(self):
        clear()
        students = get_students(self.context.config_manager.config.students_csv)

        options = []
        for i, student in enumerate(students):
            l_spaces = len(str(len(students))) - len(str(i + 1))
            options.append(MenuOption(len(options) + 1, (' ' * l_spaces) + f'{students[student].ljust(25)} : {student}', Event(), Event(), Event(), False))

        for option in options:
            print(f'{LIGHT_GREEN}[{option.number}] {CYAN}{option.text}{WHITE}')

        print()
        index = input('Enter a number to select a student: ')
        while not index.isdigit() or int(index) < 1 or int(index) > len(options):
            index = input('Enter a number to select a student: ')

        student_split = options[int(index) - 1].text.split(' : ')
        student_name = student_split[0].strip()
        student_github = student_split[1].strip()

        extra_ca_hours = prompt_for_digit('Class Activities time adjustment in hours: ')
        extra_as_hours = prompt_for_digit('Assignment time adjustment in hours: ')
        extra_ex_hours = prompt_for_digit('Exam time adjustment in hours: ')

        student_param = StudentParam(student_name, student_github, extra_ca_hours, extra_as_hours, extra_ex_hours)

        self.context.config_manager.config.extra_student_parameters.append(student_param)
        self.context.config_manager.save_config()


    def edit_param(self, student_param):
        while True:
            clear()
            name_option = MenuOption(0, f'{LIGHT_GREEN}Name: {WHITE}{student_param.name}',
                                        lambda: self.edit_param_value(student_param, 'name'),
                                        Event(), Event(), False, False)

            github_option = MenuOption(0, f'{LIGHT_GREEN}Github: {WHITE}{student_param.github}',
                                       lambda: self.edit_param_value(student_param, 'github'),
                                       Event(), Event(), False, False)

            extra_ca_option = MenuOption(1, f'{LIGHT_GREEN}Class Activities Adjustment (hr): {WHITE}{student_param.class_activity_adj}',
                                            lambda: self.edit_param_value(student_param, 'class_activity_adj', True),
                                            Event(), Event(), False)

            extra_as_option = MenuOption(2, f'{LIGHT_GREEN}Assignment Adjustment (hr): {WHITE}{student_param.assignment_adj}',
                                            lambda: self.edit_param_value(student_param, 'assignment_adj', True),
                                            Event(), Event(), False)

            extra_ex_option = MenuOption(3, f'{LIGHT_GREEN}Exam Adjustment (hr): {WHITE}{student_param.exam_adj}',
                                            lambda: self.edit_param_value(student_param, 'exam_adj', True),
                                            Event(), Event(), False)

            delete_option = MenuOption(4, f'{LIGHT_RED}Delete{WHITE}',
                                       lambda: self.edit_param_value(None, None),
                                       Event(), Event(), False)

            options = [name_option, github_option, extra_ca_option, extra_as_option, extra_ex_option, delete_option]

            for option in options:
                if option.number == 0:
                    print(f'{option.text}')
                else:
                    print(f'{LIGHT_GREEN}[{option.number}] {CYAN}{option.text}{WHITE}')

            print()
            index = input(f'Please enter a number {LIGHT_GREEN}(1-{len(options) - 2}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: ')
            if index == 'q' or index == 'quit':
                return

            while not index.isdigit() or int(index) < 1 or int(index) > len(options) - 2:
                index = input('Try again: ')
                if index == 'q' or index == 'quit':
                    return

            new_param = options[int(index) - 1 + 2].on_select()
            for i, param in enumerate(self.context.config_manager.config.extra_student_parameters):
                if param.name == student_param.name and param.github == student_param.github:
                    if new_param is None:
                        del self.context.config_manager.config.extra_student_parameters[i]
                        self.context.config_manager.save_config()
                        return
                    self.context.config_manager.config.extra_student_parameters[i] = new_param
                    self.context.config_manager.save_config()
                    student_param = new_param
                    break


    def edit_param_value(self, param, value_name, check_float=False):
        if param is None:
            return

        clear()
        print(f'{LIGHT_GREEN}Current Value: {WHITE}{getattr(param, value_name)}')
        new_value = None
        if check_float:
            new_value = prompt_for_digit('Please enter a new floatable number: ')
        else:
            new_value = input('Please enter a new value: ')

        new_param = StudentParam(param.name, param.github, param.class_activity_adj, param.assignment_adj, param.exam_adj)
        setattr(new_param, value_name, new_value)
        return new_param


    def run(self):
        self.load()
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            if user_input.lower() == 'q' or user_input.lower() == 'quit':
                self.student_csv_menu_quit = True
            handle_option_return = self.handle_option(user_input)
        clear()
