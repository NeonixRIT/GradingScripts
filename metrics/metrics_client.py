import socket
import threading
import time

from .metrics_client_proxy import MetricsProxy

class MetricsClient():
    '''
    Class that creates udp socket to www.neonix.me on port 1337 and passes that to a MetricsProxy object
    '''
    __slots__ = ['proxy', '__keep_alive_thread']

    def __init__(self, addr: str, port: int):
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.connect((addr, port))
        self.proxy = MetricsProxy(client)
        self.__start_keep_alive()


    def __start_keep_alive(self):
        self.__keep_alive_thread = KeepAliveThread(self.proxy)
        self.__keep_alive_thread.start()

    
    def quit(self):
        self.__keep_alive_thread.stop()
        self.proxy.close()


class KeepAliveThread(threading.Thread):
    __slots__ = ['proxy', 'interval', 'kill']

    def __init__(self, proxy: MetricsProxy, interval=5):
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