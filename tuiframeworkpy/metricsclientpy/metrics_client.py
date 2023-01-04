import socket
import threading
import time

from .metrics_client_proxy import MetricsProxy
# from metrics_client_proxy import MetricsProxy # for testing

INTERVAL = 5  # how often to repeat keep alive time in seconds


class MetricsClient:
    """
    Class that creates udp socket to www.neonix.me on port 1337 and passes that to a MetricsProxy object
    """
    __slots__ = ['addr', 'port', 'encrypt', 'proxy', '__keep_alive_thread', '__proxy_methods']

    def __init__(self, addr: str, port: int, proxy_methods: list, encrypt: bool = True):
        self.addr = addr
        self.port = port
        self.__proxy_methods = proxy_methods
        self.encrypt = encrypt
        self.proxy = None

    def __iadd__(self, func):
        self.__proxy_methods.append(func)
        return self

    def __start_keep_alive(self):
        self.__keep_alive_thread = KeepAliveThread(self.proxy, INTERVAL)
        self.__keep_alive_thread.start()

    def initialize(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.connect((self.addr, self.port))
        self.proxy = MetricsProxy(client, INTERVAL, self.encrypt, self.__proxy_methods)
        self.__start_keep_alive()

    def quit(self):
        self.__keep_alive_thread.stop()
        self.proxy.close()


class KeepAliveThread(threading.Thread):
    __slots__ = ['proxy', 'interval', 'kill']

    def __init__(self, proxy: MetricsProxy, interval: int):
        self.proxy = proxy
        self.interval = interval
        self.kill = False
        super().__init__(daemon=True)

    def run(self):
        time.sleep(self.interval)
        while not self.kill:
            self.proxy.keep_alive()
            time.sleep(self.interval)

    def stop(self):
        self.kill = True
