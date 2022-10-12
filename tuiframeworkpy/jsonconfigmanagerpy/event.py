class Event:
    __slots__ = ['__funcs']

    def __init__(self):
        self.__funcs = []


    def __call__(self) -> list:
        return [func() for func in self.__funcs]


    def __repr__(self) -> str:
        string = 'Event('
        for func in self.__funcs:
            string += f'{func.__name__}, '
        return string[:-2] + ')'


    def __iadd__(self, func):
        if func not in self.__funcs:
            self.__funcs.append(func)
        return self
