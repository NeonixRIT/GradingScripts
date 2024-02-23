from .colors import LIGHT_RED, WHITE

from .dependency import Dependency
from .dependency import DependencyInstallationError, IndependentDependencyError


class DependencyManager:
    def __init__(self, dependencies: list[Dependency], verbose: bool = False):
        self.dependencies = dependencies
        self.verbose = verbose
        self.update_verbose(verbose=verbose)

    def update_verbose(self, verbose: bool):
        self.verbose = verbose
        for dependency in self.dependencies:
            dependency.verbose = verbose

    def check_and_install(self):
        try:
            for dependency in self.dependencies:
                if self.verbose:
                    print(f'Checking dependency: {dependency.package}')
                installed, correct_version = dependency.check()
                if not installed or not correct_version:
                    print(f'{LIGHT_RED}WARNING: Dependency {dependency.package} is not installed or is not the correct version. Attempting to install...{WHITE}')
                    dependency.install(correct_version)
        except IndependentDependencyError:
            # print(ide.message)
            print(f'{LIGHT_RED}FATAL: A Dependency ')
            exit(1)
        except DependencyInstallationError as die:
            print(die.message)
            exit(1)
        except (Exception, KeyboardInterrupt) as e:
            print(f'{LIGHT_RED}FATAL: An unknown error occurred\n{e}{WHITE}')
            exit(1)
