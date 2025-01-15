import os
import re
import subprocess
import sys

from .colors import LIGHT_RED, CYAN, WHITE
from .version import Version


class DependencyInstallationError(Exception):
    __slots__ = ['message']

    def __init__(self, dependency, args: list, cpe: subprocess.CalledProcessError):
        self.message = f'{LIGHT_RED}FATAL: Failed to install dependency: {dependency.package}{WHITE}\n\n{CYAN}args: {args}{WHITE}\n\n{cpe}'


class IndependentDependencyError(Exception):
    __slots__ = ['message']

    def __init__(self, dependency):
        self.message = f'{LIGHT_RED}FATAL: Dependency is missing or out of date and cannot be installed automatically: {dependency.package}>={dependency.req_version}{WHITE}'


CACHED_RESULTS = {}
UV_CHECKED = False
UV_INSTALLED = False


class Dependency:
    def __init__(
        self,
        package,
        req_version: str,
        package_manager_cmd: str,
        version_flag: str = '--version',
        version_regex: str = r'(\d+\.\d+\.\d+)',
    ):
        self.package = package
        self.req_version = Version(req_version)
        self.package_manager_cmd = package_manager_cmd
        self.version_flag = version_flag
        self.version_regex = version_regex
        self.installed = False
        self.up_to_date = False

    def install(self, upgrade: bool = False):
        global UV_CHECKED, UV_INSTALLED

        if not self.package_manager_cmd:
            raise IndependentDependencyError(self)

        # Decide sub_command for non-pip package managers
        sub_command = 'install' if not upgrade else 'upgrade'

        if self.package_manager_cmd == 'pip':
            # If we haven't yet checked for `uv`, do it once
            if not UV_CHECKED:
                try:
                    subprocess.check_call(['uv', '--help'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    UV_INSTALLED = True
                except FileNotFoundError:
                    UV_INSTALLED = False
                UV_CHECKED = True

            # Build the args for pip
            if UV_INSTALLED:
                args = ['uv', 'pip', 'install']
            else:
                args = [sys.executable, '-m', 'pip', 'install']
            if upgrade:
                args.append('--upgrade')
            args.append(self.package)
        else:
            # For non-pip package managers, use the sub_command
            args = [self.package_manager_cmd, sub_command, self.package]

        try:
            subprocess.check_call(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as cpe:
            raise DependencyInstallationError(self, args, cpe) from cpe

    def check(self) -> tuple[bool, bool]:
        global UV_CHECKED, UV_INSTALLED

        # Determine the command to run for version checking
        if self.package_manager_cmd == 'pip':
            # If we've never checked for 'uv' before, do so
            if not UV_CHECKED:
                try:
                    subprocess.check_call(('uv', '--version'), stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                    UV_INSTALLED = True
                except FileNotFoundError:
                    UV_INSTALLED = False
                UV_CHECKED = True

            # Now pick the freeze command
            if UV_INSTALLED:
                args = ('uv', 'pip', 'freeze', '--color=never')
            else:
                args = (sys.executable, '-m', 'pip', 'freeze', '--no-color')
        else:
            # For non-pip dependencies, just call '--version' (or version_flag)
            args = (self.package, self.version_flag)

        try:
            # Check cache first
            if args in CACHED_RESULTS:
                result = CACHED_RESULTS[args]
            else:
                result = subprocess.check_output(args).decode().strip()
                CACHED_RESULTS[args] = result

            # Extract the current version from the result
            if self.package_manager_cmd == 'pip':
                pattern = f'{self.package}=={self.version_regex}'
            else:
                pattern = f'{self.version_regex}'
            match = re.findall(pattern, result)
            if not match:
                # If we can’t find a matching version, treat it as not installed
                raise IndexError

            current_version = Version(match[0])

            if self.verbose:
                print(f'    args: {args}')
                print(f'    Current version: {current_version}')

            # Compare the found version with the required version
            if current_version >= self.req_version:
                self.installed = True
                self.up_to_date = True
                if self.verbose:
                    print(f'{self.package} is installed and up to date\n')
                return self.installed, self.up_to_date
            else:
                self.installed = True
                self.up_to_date = False
                if self.verbose:
                    print(f'{self.package} is installed but out of date\n')
                return self.installed, self.up_to_date

        except (subprocess.CalledProcessError, IndexError):
            # Either the command failed or the version wasn’t in the output
            self.installed = False
            self.up_to_date = False
            if self.verbose:
                print(f'{self.package} is not installed\n')
            return self.installed, self.up_to_date
