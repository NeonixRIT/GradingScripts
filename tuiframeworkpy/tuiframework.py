from pathlib import Path

from .dependencymanagerpy import DependencyManager, Dependency
from .jsonconfigmanagerpy import ConfigManager, ConfigEntry

from .model.colors import CYAN, LIGHT_RED, WHITE
from .model.context import Context
from .model.event import Event
from .model.menu import Menu
from .model.submenu import SubMenu
from .model.utils import print_updates, clear

from traceback import format_exc
# TODO: Add logging module


class TUI:
    def __init__(
        self,
        version,
        dependencies: list[Dependency],
        config_path: str,
        config_entries: list[ConfigEntry],
        default_paths: list[str],
    ) -> None:
        self.version = version

        for directory in default_paths:
            Path(directory).mkdir(parents=True, exist_ok=True)

        requests = Dependency('requests', '2.32.0', 'pip') # for versionmanagerpy
        versionamanagerpy = Dependency('versionmanagerpy', '1.0.2', 'pip') # for update checking
        depends_man = DependencyManager([requests, versionamanagerpy] + dependencies)

        debug_entry = ConfigEntry(
            'debug',
            'Debug',
            False,
            'Would you like to enable debug mode (not recommended)?',
            is_bool_prompt=True,
        )
        conf_man = ConfigManager(config_path, config_entries + [debug_entry])

        self.context = Context(conf_man, depends_man, self)

        self.on_error = Event()
        self.on_quit = Event()
        self.on_start = Event()

        self.menus: dict[int, Menu]
        self.menus = {}

        self.update_instance = False

    def add_menu(self, menu: Menu) -> None:
        menu.context = self.context
        self.menus[menu.id] = menu

    def add_submenu(self, submenu: SubMenu, parent: Menu):
        submenu.parent = parent
        submenu.context = self.context
        self.menus[submenu.id] = submenu

    def open_menu(self, menu_id: int):
        self.menus[menu_id].open()

    def start(self) -> None:
        try:
            self.on_start()

            self.context.config_manager.initialize()
            self.context.dependency_manager.update_verbose(self.context.config_manager.config.debug)
            self.context.dependency_manager.check_and_install()
            self.context.config_manager.depends_loaded = True
            if self.context.config_manager.config.debug:
                input('Press enter to continue...')
            from versionmanagerpy import versionmanager, VersionManager

            vm = VersionManager('NeonixRIT', 'GradingScripts', self.version)

            update_status = None
            try:
                update_status = vm.check_status()
            except Exception:
                print(f'{LIGHT_RED}WARNING: Unable to check for update.{WHITE}')
            self.context.update_status = update_status
            if update_status == versionmanager.Status.OUTDATED:
                print_updates(self.version, self)

            if self.update_instance:
                exit()

            for menu in filter(lambda x: self.menus[x].preload, self.menus):
                self.menus[menu].load()
            self.menus[0].open()
        except (ConnectionError, KeyboardInterrupt, Exception) as e:
            clear()
            self.on_error()
            try:
                client_log_handler = getattr(self.menus[10].client, 'log_file_handler', None)
                if client_log_handler is not None:
                    client_log_handler.write(f'*** ERROR OCCURED ***\n{format_exc()}')
                    client_log_handler.close()
            except Exception:
                pass
            if not isinstance(e, KeyboardInterrupt):
                print(f'\n{LIGHT_RED}FATAL: Unknown Error Occured.{WHITE}\n\n{CYAN}{e}{WHITE}\n')
                if getattr(self.context.config_manager.config, 'debug', True):
                    raise e
                self.menus[0].quit()
