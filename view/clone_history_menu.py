from .clone_report import CloneReport

from tuiframeworkpy import SubMenu, Event, MenuOption
from tuiframeworkpy import LIGHT_RED, LIGHT_GREEN, CYAN, WHITE, clear


class CloneHistoryMenu(SubMenu):
    def __init__(self, id):
        clear_history_options = MenuOption(1, 'Clear History', Event(), Event(), Event(), pause=False)

        clear_history_options.on_select += lambda: self.context.config_manager.set_config_value('clone_history', [])
        clear_history_options.on_exit += self.load
        self.local_option = [clear_history_options]

        SubMenu.__init__(self, id, 'Clone History', self.local_option, Event(), Event(), preload=False)
        assign_str = 'Assignment:dry_run'.ljust(25)
        due_str = 'Due'.ljust(20)
        curr_str = 'Current'.ljust(20)
        self.legend = f'{CYAN}{assign_str}{LIGHT_GREEN}{due_str}{LIGHT_RED}{curr_str}{WHITE}'
        self.on_enter += self.load

    def load(self):
        self.history_options = self.build_preset_options()
        self.local_option[0].number = len(self.history_options) + 1

        options = self.history_options + self.local_option
        self.options = dict()
        for menu_option in options:
            self.options[menu_option.number] = menu_option
        self.max_options = len(options)
        self.prompt_string = self.prompt_string = f'Please enter a number {LIGHT_GREEN}({self.min_options}-{self.max_options}){WHITE} or {LIGHT_RED}q/quit{WHITE} to return to the previous menu: '
        self.invalid_input_string = f'You entered an invalid option.\n\nPlease enter a number between {self.min_options} and {self.max_options}.\nPress enter to try again.'

    def build_preset_options(self) -> list:
        options = []
        report: CloneReport
        for i, report in enumerate(self.context.config_manager.config.clone_history[::-1]):
            option_event = Event()

            report_str = f'{CYAN}Assignment Name: {report.assignment_name}\n' + \
                         f'Due Date: {report.due_date}\n' + \
                         f'Due Time: {report.due_time}\n' + \
                         f'Current Date: {report.current_date}\n' + \
                         f'Current Time: {report.current_time}\n' + \
                         f'Dry Run: {report.dry_run}\n' if getattr(report, 'dry_run', False) else f'Tag Name: {getattr(report, 'tag_name', 'Error')}\n' + \
                         f'Student CSV: {report.student_csv}{WHITE}\n\n'

            for line in report.outputs_log:
                report_str += f'{line}\n'

            def on_select(bound_report_str=report_str):
                print(bound_report_str)
                input('Press enter to continue...')
                clear()

            option_event += on_select
            option = MenuOption(i + 1, report_summary(report), option_event, Event(), Event(), pause=False)
            options.append(option)
        return options


def report_summary(report):
    assignment_tag_str = f'{report.assignment_name}:{report.dry_run}'.ljust(25) if getattr(report, 'dry_run', False) else f'{report.assignment_name}'.ljust(25)
    due_str = f'{report.due_date} {report.due_time}'.ljust(20)
    curr_str = f'{report.current_date} {report.current_time}'.ljust(20)
    return f'{CYAN}{assignment_tag_str}{LIGHT_GREEN}{due_str}{LIGHT_RED}{curr_str}{WHITE}'
