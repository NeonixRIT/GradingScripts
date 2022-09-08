# from event import Event
# from menu import Menu
# from menu_option import MenuOption
# from submenu import SubMenu
import model

from .clone_menu import CloneMenu
from .setup import setup

from pathlib import Path

class MainMenu(model.Menu):
    def __init__(self):
        setup_complete = Path('./data/config.json').exists()

        clone_menu = CloneMenu()
        clone_repos_event = model.Event()
        clone_repos_event += clone_menu.run
        clone_repos = model.MenuOption(1, 'Clone Repos', clone_repos_event, False, setup_complete)

        add_menu = CloneMenu() # AddMenu()
        add_event = model.Event()
        add_event += add_menu.run
        add = model.MenuOption(2, 'Add Files', add_event, False, False)

        manage_menu = CloneMenu() # ManageMenu()
        manage_repos_event = model.Event()
        manage_repos_event += manage_menu.run
        manage_repos = model.MenuOption(3, 'Repo Manager', manage_repos_event, False, setup_complete)

        config_menu = CloneMenu() # ConfigMenu()
        config_event = model.Event()
        config_event += config_menu.run
        config = model.MenuOption(4, 'Edit Config', config_event, False, setup_complete)

        def update_options():
            setup_complete = Path('./data/config.json').exists()
            clone_repos.enabled = setup_complete
            # add.enabled = setup_complete
            manage_repos.enabled = setup_complete
            config.enabled = setup_complete

        setup_config_event = model.Event()
        setup_config_event += setup
        setup_config_event += update_options
        setup_config = model.MenuOption(5, 'Run Setup', setup_config_event)

        options = [clone_repos, add, manage_repos, config, setup_config]
        model.Menu.__init__(self, 'GCIS Grading Scripts v2.0', options)
        # TODO check update, print version, etc
