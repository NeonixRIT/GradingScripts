# print current config into w/ token censored
# edit each config value
# import old settings

import model
import os

from .select_csv_menu import SelectCSVMenu

class ConfigMenu(model.SubMenu):
    __slots__ = ['config']

    def __init__(self):
        self.config = model.utils.read_config('./data/config.json')

        censored_token = model.utils.censor_string(self.config.token)

        edit_token_event = model.Event()
        edit_token_event += lambda: self.edit_config_value('token')
        edit_token = model.MenuOption(1, f'Token: {censored_token}', edit_token_event, False)

        edit_org_event = model.Event()
        edit_org_event += lambda: self.edit_config_value('organization')
        edit_org = model.MenuOption(2, f'Organization: {self.config.organization}', edit_org_event, False)

        edit_csv_path_event = model.Event()
        edit_csv_path_event += lambda: self.edit_config_value('students_csv')
        edit_csv_path = model.MenuOption(3, f'Students CSV Path: {self.config.students_csv}', edit_csv_path_event, False)

        edit_out_dir_event = model.Event()
        edit_out_dir_event += lambda: self.edit_config_value('out_dir')
        edit_out_dir = model.MenuOption(4, f'Output Directory: {self.config.out_dir}', edit_out_dir_event, False)

        def update_options():
            edit_token.text = f'Token: {model.utils.censor_string(self.config.token)}'
            edit_org.text = f'Organization: {self.config.organization}'
            edit_csv_path.text = f'Students CSV Path: {self.config.students_csv}'
            edit_out_dir.text = f'Output Directory: {self.config.out_dir}'

        edit_token.on_select += update_options
        edit_org.on_select += update_options
        edit_csv_path.on_select += update_options
        edit_out_dir.on_select += update_options

        model.SubMenu.__init__(self, 'Change Config Values', [edit_token, edit_org, edit_csv_path, edit_out_dir])


    def edit_config_value(self, value_name: str):
        model.utils.clear()

        student_csv_menu_quit = True
        if value_name == 'students_csv':
            if len(os.listdir('./data/csvs/')) == 0:
                self.set_config_value(value_name, input('Enter the desired new value: '))
                return
            select_csv_menu = SelectCSVMenu(self.config)
            select_csv_menu.run()
            student_csv_menu_quit = select_csv_menu.student_csv_menu_quit

        if student_csv_menu_quit:
            self.set_config_value(value_name, input('Enter the desired new value: '))


    def set_config_value(self, value_name, new_value):
        model.utils.clear()
        setattr(self.config, value_name, new_value)
        model.utils.save_config(self.config)
        self.config = model.utils.read_config('./data/config.json')
        model.utils.clear()
