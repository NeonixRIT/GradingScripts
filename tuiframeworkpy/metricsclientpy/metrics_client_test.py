from metrics_client import MetricsClient

import time

def main():
    try:
        client = MetricsClient('127.0.0.1', 13370)
        while True:
            client.proxy.repos_cloned(1)
            time.sleep(20)
    except KeyboardInterrupt:
        client.quit()


if __name__ == '__main__':
    main()
