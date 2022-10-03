from metrics.metrics_client import MetricsClient
import model
import view
from metrics import MetricsClient

METRICS_ADDR = 'www.neonix.me'
METRICS_PORT = 1337

def main():
    metrics_client = MetricsClient(METRICS_ADDR, METRICS_PORT)
    try:
        main_menu = view.MainMenu(metrics_client)
        main_menu.run()
        metrics_client.quit()
    except KeyboardInterrupt:
        model.utils.clear()
        print(main_menu.quit_string)
        metrics_client.proxy.error_handled()
        metrics_client.quit()
    except Exception as e:
        print(f'{model.colors.LIGHT_RED}FATAL: An unknown error has occured.{model.colors.WHITE}\n    > {e}')
        metrics_client.proxy.error_handled()
        metrics_client.quit()
        raise e


if __name__ == '__main__':
    main()
