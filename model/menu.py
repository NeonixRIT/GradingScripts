from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .utils import clear

class Menu:
    __slots__ = ['name', 'min_options', 'max_options', 'options', 'prompt_string', 'quit_string', 'invalid_input_string']

    def __init__(self, name: str, options: list):
        self.name = name
        self.options = options
        self.min_options = 1
        self.max_options = len(options)

        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to quit the program: '
        self.quit_string = 'Closing...\nReturning to shell.\n\nHave a wonderful day!'
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'


    def __str__(self) -> str:
        clear()
        middle_len = len(self.name) + 2 + 28
        out_str = ('*' * middle_len) + '\n' + \
            f'************** {LIGHT_GREEN}{self.name}{WHITE} **************\n' + \
            ('*' * middle_len) + '\n\n' + \
            'Enter Selection:\n'
        for option in self.options:
            out_str += f'    {option}\n'
        out_str += '\n'
        return out_str


    def get_option(self) -> str:
        print(self)
        return input(self.prompt_string).lower()


    def handle_invalid_option(self) -> None:
        '''
        Message to notify user of invalid input
        '''
        input(self.invalid_input_string)


    def __quit(self) -> None:
        clear()
        print(self.quit_string)
        input('Press enter to continue...')
        clear()


    def handle_option(self, user_option: str) -> tuple:
        user_option_int = 0
        if user_option == 'q' or user_option == 'quit':
            self.__quit()
            return (False, [])
        elif not user_option:
            self.handle_invalid_option()
            return (True, [])
        else:
            try:
                user_option_int = int(user_option)
                if user_option_int not in range(self.min_options, self.max_options + 1):
                    self.handle_invalid_option()
                    return (True, [])
            except ValueError:
                self.handle_invalid_option() # if user input is not an int
                return (True, [])

        clear()
        result = self.options[user_option_int - 1]()
        if self.options[user_option_int - 1].pause:
            input('Press enter to continue...')
        return (True, result)


    def run(self) -> None:
        handle_option_return = (True, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            handle_option_return = self.handle_option(user_input)
        clear()
