from pathlib import Path

from .dependencymanagerpy import DependencyManager, Dependency
from .jsonconfigmanagerpy import ConfigManager, ConfigEntry
from .metricsclientpy import MetricsClient

from .model.colors import CYAN, LIGHT_RED, WHITE
from .model.context import Context
from .model.event import Event
from .model.menu import Menu
from .model.submenu import SubMenu
from .model.utils import print_updates, clear

# TODO: Add logging module


class TUI:
    def __init__(self, version, dependencies: list[Dependency], config_path: str, config_entries: list[ConfigEntry], metrics_addr: str, metrics_port: int, proxy_methods: list, metrics_encrypt: bool, default_paths: list[str]) -> None:
        self.version = version

        for directory in default_paths:
            Path(directory).mkdir(parents=True, exist_ok=True)

        versionamanagerpy = Dependency('versionmanagerpy', '1.0.2', 'pip')
        depends_man = DependencyManager([versionamanagerpy] + dependencies)

        debug_entry = ConfigEntry('debug', 'Debug', False, 'Would you like to enable debug mode (not recommended)?', is_bool_prompt=True)
        metrics_entry = ConfigEntry('metrics_api', 'Metrics API', True, 'Would you like to contribute to Metrics data?', prompt=True, is_bool_prompt=True)
        conf_man = ConfigManager(config_path, config_entries + [debug_entry, metrics_entry])

        metrics_client = MetricsClient(metrics_addr, metrics_port, proxy_methods, metrics_encrypt)
        self.__metrics_addr = metrics_addr
        self.__metrics_port = metrics_port
        self.__proxy_methods = proxy_methods
        self.__metrics_encrypt = metrics_encrypt
        if not metrics_addr or not metrics_port:
            metrics_client = None

        self.context = Context(conf_man, depends_man, metrics_client, self)

        self.on_error = Event()
        self.on_quit = Event()
        self.on_start = Event()

        self.menus: dict[int, Menu]
        self.menus = {}

    def add_menu(self, menu: Menu) -> None:
        menu.context = self.context
        self.menus[menu.id] = menu

    def add_submenu(self, submenu: SubMenu, parent: Menu):
        submenu.parent = parent
        submenu.context = self.context
        self.menus[submenu.id] = submenu

    def open_menu(self, menu_id: int):
        self.menus[menu_id].open()

    def update_metrics_client(self):
        if self.context.config_manager.config.metrics_api:
            self.context.metrics_client = MetricsClient(self.__metrics_addr, self.__metrics_port, self.__proxy_methods, self.__metrics_encrypt)
            self.context.metrics_client.initialize()
        else:
            self.context.metrics_client = None

    def start(self) -> None:
        try:
            self.on_start()
            self.context.dependency_manager.check_and_install()
            from versionmanagerpy import versionmanager, VersionManager
            vm = VersionManager('NeonixRIT', 'GradingScripts', self.version)

            update_status = None
            try:
                update_status = vm.check_status()
            except Exception:
                print(f'{LIGHT_RED}WARNING: Unable to check for update.{WHITE}')
            self.context.update_status = update_status
            if update_status == versionmanager.Status.OUTDATED:
                print_updates(self.version)
            self.context.config_manager.initialize()

            if self.context.config_manager.config.metrics_api:
                self.context.metrics_client.initialize()
                self.on_error += self.context.metrics_client.proxy.error_handled

            for menu in self.menus:
                self.menus[menu].load()
            self.menus[0].open()
        except (ConnectionError, KeyboardInterrupt, Exception) as e:
            clear()
            self.on_error()
            if not isinstance(e, KeyboardInterrupt):
                print(f'\n{LIGHT_RED}FATAL: Unknown Error Occured.{WHITE}\n\n{CYAN}{e}{WHITE}\n')
                if getattr(self.context.config_manager.config, 'debug', True):
                    raise e
            self.menus[0].quit()
