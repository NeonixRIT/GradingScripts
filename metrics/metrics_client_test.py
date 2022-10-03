from metrics_client import MetricsClient

import time

def main():
    client = MetricsClient('127.0.0.1', 1337)
    client.proxy.error_handled()
    while True:
        client.proxy.repos_cloned(1)
        time.sleep(20)


if __name__ == '__main__':
    main()
