from dataclasses import dataclass


@dataclass(
    init=True,
    repr=False,
    eq=False,
    order=False,
    unsafe_hash=True,
    frozen=False,
    match_args=False,
    kw_only=False,
    slots=False,
)
class StudentParam:
    name: str
    github: str
    class_activity_adj: float = 0
    assignment_adj: float = 0
    exam_adj: float = 0
