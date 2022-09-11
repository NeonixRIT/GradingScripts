import model
import view

def main():
    try:
        main_menu = view.MainMenu()
        main_menu.run()
    except KeyboardInterrupt:
        model.utils.clear()
        print(main_menu.quit_string)
    except Exception as e:
        print(f'{model.colors.LIGHT_RED}FATAL: An unknown error has occured.{model.colors.WHITE}\n    > {e}')


if __name__ == '__main__':
    main()
