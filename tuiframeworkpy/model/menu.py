import sys

from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .context import Context
from .event import Event
from .utils import clear
from .menu_option import MenuOption


class Menu:
    __slots__ = ['context', 'id', 'name', 'min_options', 'max_options', 'options', 'on_enter', 'on_exit', 'prompt_string', 'quit_string', 'invalid_input_string', 'disabled_option_string', 'legend', 'preload']

    def __init__(self, id: int, name: str, options: list[MenuOption], on_enter: Event = None, on_exit: Event = None, preload = True, legend: str = ''):
        self.context: Context
        self.name = name
        self.id = id

        self.options: dict[int, MenuOption]
        self.options = {}
        for menu_option in options:
            self.options[menu_option.number] = menu_option

        self.min_options = 1
        self.max_options = len(options)

        if on_enter is None:
            on_enter = Event()
        if on_exit is None:
            on_exit = Event()
        self.on_enter = on_enter
        self.on_exit = on_exit
        self.legend = legend
        self.preload = preload

        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to quit the program: '
        self.quit_string = 'Closing...\nReturning to shell.\n\nHave a wonderful day!'
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'
        self.disabled_option_string = 'This option is currently disabled.\nThis either means this feature is not implemented or your system does not meet the requirements to use this option.\nPress enter to select a different option.'

    def __str__(self) -> str:
        clear()
        middle_len = len(self.name) + 2 + 28
        middle_len -= len(LIGHT_RED) if LIGHT_RED in self.name else 0
        middle_len -= len(LIGHT_GREEN) if LIGHT_GREEN in self.name else 0
        middle_len -= len(CYAN) if CYAN in self.name else 0
        middle_len -= len(WHITE) if WHITE in self.name else 0
        legend_str = f'Legend: {self.legend}\n' if self.legend else ''
        out_str = ('*' * middle_len) + '\n' + \
            f'************** {LIGHT_GREEN}{self.name}{WHITE} **************\n' + \
            ('*' * middle_len) + '\n\n' + \
            legend_str + \
            'Enter Selection:\n'
        for option in self.options:
            out_str += f'    {self.options[option]}\n'
        out_str += '\n'
        return out_str

    def load(self) -> None:
        raise NotImplementedError

    def get_option(self) -> str:
        print(self)
        return input(self.prompt_string).lower()

    def handle_invalid_option(self) -> None:
        """
        Message to notify user of invalid input
        """
        input(self.invalid_input_string)

    def handle_disabled_option(self) -> None:
        """
        Message to notify user of invalid input
        """
        input(self.disabled_option_string)

    def quit(self) -> None:
        print(self.quit_string)
        input('Press enter to continue...')
        clear()
        self.on_exit()

    def handle_option(self, user_option: str) -> tuple:
        user_option_int = 0
        if user_option == 'q' or user_option == 'quit':
            self.quit()
            return False, []
        elif not user_option:
            self.handle_invalid_option()
            return True, []
        else:
            try:
                user_option_int = int(user_option)
                if user_option_int not in range(self.min_options, self.max_options + 1):
                    self.handle_invalid_option()
                    return True, []
            except ValueError:
                self.handle_invalid_option()  # if user input is not an int
                return True, []

        clear()
        if not self.options[user_option_int].enabled:
            self.handle_disabled_option()
            return True, []
        result = self.options[user_option_int]()
        if self.options[user_option_int].pause:
            input('Press enter to continue...')
        return True, result

    def open(self) -> None:
        self.on_enter()
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            handle_option_return = self.handle_option(user_input)
        clear()
        sys.exit(0)
