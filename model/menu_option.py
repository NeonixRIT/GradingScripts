from .colors import LIGHT_GREEN, LIGHT_RED, CYAN, WHITE
from .event import Event

class MenuOption:
    __slots__ = ['number', 'text', 'on_select', 'pause', 'enabled']

    def __init__(self, number: int, text: str, on_select: Event, pause: bool = True, enabled: bool = True):
        self.number = number
        self.text = text
        self.on_select = on_select
        self.pause = pause
        self.enabled = enabled


    def __str__(self) -> str:
        color = LIGHT_GREEN if self.enabled else LIGHT_RED
        return f'{color}[{self.number}]{WHITE} {self.text}'


    def __repr__(self) -> str:
        return f'MenuOption(number: {self.number}, text: {self.text}, on_select: {self.on_select})'


    def __call__(self) -> list:
        return self.on_select()
