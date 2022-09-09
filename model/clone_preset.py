# preset consists of output file suffix, clone time, prefix name, csv file or default
class ClonePreset:
    __slots__ = ['file_suffix', 'clone_time', 'name', 'csv_path']

    def __init__(self, name, file_suffix, clone_time, csv_path):
        self.name = name
        self.file_suffix = file_suffix
        self.clone_time = clone_time
        self.csv_path = csv_path
