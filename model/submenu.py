from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .menu import Menu
from .utils import clear

class SubMenu(Menu):
    __slots__ = ['parent', 'only_one_prompt']

    def __init__(self, name: str, options: list, only_one_prompt: bool = False):
        Menu.__init__(self, name, options)
        self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '
        self.quit_string = ''
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'
        self.only_one_prompt = only_one_prompt


    def __quit(self):
        clear()


    def handle_option(self, user_option: str) -> tuple:
        user_option_int = 0
        if user_option == 'q' or user_option == 'quit':
            self.__quit()
            return (False, user_option_int, [])
        elif not user_option:
            self.handle_invalid_option()
            return (True, user_option_int, [])
        else:
            try:
                user_option_int = int(user_option)
                if user_option_int not in range(self.min_options, self.max_options + 1):
                    self.handle_invalid_option()
                    return (True, user_option_int, [])
            except ValueError:
                self.handle_invalid_option() # if user input is not an int
                return (True, user_option_int, [])

        clear()
        result = self.options[user_option_int]()
        if self.options[user_option_int].pause:
            input('Press enter to continue...')
        return (not self.only_one_prompt, user_option_int, result)


    def run(self):
        handle_option_return = (True, 0, [])
        while handle_option_return[0]:
            user_input = self.get_option()
            handle_option_return = self.handle_option(user_input)
        clear()
