import model

class CloneMenu(model.SubMenu):
    __slots__ = ['presets']

    def __init__(self):
        self.presets = []
        # read config for presets and other info
        # whenever add/delete preset, update options list
        clone_repos_event = model.Event()
        clone_repos_event += lambda: print('test event')
        clone_repos = model.MenuOption(len(self.presets) + 1, 'Manage Presets', clone_repos_event)

        # after clone preset selected or no preset
        # prompt for missing info and clone
        # log output info
        # options = [model.MenuOption(i, preset.name, lambda: type(1337)) for i, preset in enumerate(self.presets)].append(clone_repos)
        # change lambda to clone repo func with info from presets/config passed in
        model.SubMenu.__init__(self, 'Clone Presets', [clone_repos])
