class Version:
    """
    Object representing a version number used to make handling Project versions easier
    """

    __slots__ = ['__version_list', '__version_str']

    def __init__(self, version='0.0.0', separator='.'):
        self.__version_str = version
        self.__version_list = list(version.split(separator))

    def __str__(self) -> str:
        return self.__version_str

    def __repr__(self) -> str:
        return f'Version[{self.__version_str}, {self.__version_list}]'

    def __lt__(self, other) -> bool:
        """
        Compare each version category to tell if local version is less than, equal to, or greater than the latest GitHub release
        """
        if not isinstance(other, Version):
            return False

        for i in range(len(self.__version_list)):
            version_number = int(self.__version_list[i])
            latest_version_number = int(other.__version_list[i])
            if version_number < latest_version_number:
                return True
            elif version_number > latest_version_number:
                return False
        return False

    def __le__(self, other) -> bool:
        if not isinstance(other, Version):
            return False
        return self < other or self == other

    def __ge__(self, other) -> bool:
        if not isinstance(other, Version):
            return False
        return self > other or self == other

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            return False

        return repr(self) == repr(other)
