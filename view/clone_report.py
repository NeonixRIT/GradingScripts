from dataclasses import dataclass


@dataclass(init=True, repr=False, eq=False, order=False, unsafe_hash=True, frozen=True,
           match_args=False, kw_only=False, slots=False)
class CloneReport:
    assignment_name: str = ''
    due_date: str = ''
    due_time: str = ''
    current_date: str = ''
    current_time: str = ''
    tag_name: str = ''
    student_csv: str = ''
    outputs_log: tuple = ()
