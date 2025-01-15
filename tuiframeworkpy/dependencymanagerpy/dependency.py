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
        args = []

        sub_command = 'install' if not upgrade else 'upgrade'
        if self.package_manager_cmd == 'pip':
            try:
                subprocess.check_call(['uv', '--help'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                args = ['uv', 'pip', 'install', self.package]
            except FileNotFoundError:
                args = [sys.executable, '-m', 'pip', 'install', self.package, '--upgrade']
        else:
            args = [self.package_manager_cmd, sub_command, self.package]

        if not self.package_manager_cmd:
            raise IndependentDependencyError(self)

        try:
            subprocess.check_call(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as cpe:
            raise DependencyInstallationError(self, args, cpe) from cpe

    def check(self) -> tuple[bool, bool]:
        args = []
        if self.package_manager_cmd == 'pip':
            try:
                subprocess.check_call(('uv', '--version'), stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                args = ('uv', 'pip', 'freeze', '--color=never')
            except FileNotFoundError:
                args = (sys.executable, '-m', 'pip', 'freeze', '--no-color')
        else:
            args = (self.package, self.version_flag)

        try:
            current_version = None
            if args in CACHED_RESULTS:
                if self.package_manager_cmd == 'pip':
                    current_version = re.findall(f'{self.package}=={self.version_regex}', CACHED_RESULTS[args])
                else:
                    current_version = re.findall(f'{self.version_regex}', CACHED_RESULTS[args])
            else:
                result = subprocess.check_output(args).decode().strip()
                CACHED_RESULTS[args] = result
                if self.package_manager_cmd == 'pip':
                    current_version = re.findall(f'{self.package}=={self.version_regex}', CACHED_RESULTS[args])
                else:
                    current_version = re.findall(f'{self.version_regex}', CACHED_RESULTS[args])
            if self.verbose:
                print(f'    args: {args}')
                print(f'    Current version: {current_version}')
            current_version = Version(current_version[0])
            if current_version >= self.req_version:
                self.installed = True
                self.up_to_date = True
                if self.verbose:
                    print(f'{self.package} is installed and up to date\n')
                return self.installed, self.up_to_date
            if self.verbose:
                print(f'{self.package} is installed but out of date\n')
            self.installed = True
            self.up_to_date = False
            return self.installed, self.up_to_date
        except (subprocess.CalledProcessError, IndexError):
            self.installed = False
            self.up_to_date = False
            if self.verbose:
                print(f'{self.package} is not installed\n')
            return self.installed, self.up_to_date
