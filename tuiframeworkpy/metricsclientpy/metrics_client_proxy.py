import types
import platform
import hashlib

from .client_duplexer import ClientDuplexer
# from duplexer import Duplexer # for testing

from socket import socket

class MetricsProxy(ClientDuplexer):
    '''
    ClientProxy is a class that takes a socket as a parameter and sends information to the server
    '''
    __slots__ = ['client', 'interval', '__UUID']


    def __init__(self, socket: socket, interval: int, encrypt: bool, proxy_methods: list):
        self.client = socket
        self.interval = interval
        self.__UUID = hashlib.sha256(f'{platform.machine()}:{platform.processor()}:{platform.system()}:{platform.node()}'.encode()).hexdigest()

        for method in proxy_methods:
            self += method

        ClientDuplexer.__init__(self, socket, encrypt)
        self.connect()


    def __iadd__(self, func):
        setattr(self, func.__name__, types.MethodType(func, self))
        return self


    def connect(self):
        self.send(f'CONNECT {self.interval} {self.__UUID}')


    def error_handled(self):
        self.send('ERROR')


    def keep_alive(self):
        self.send(f'KEEPALIVE {self.__UUID}')


    def __disconnect(self):
        self.send(f'DISCONNECT {self.__UUID}')


    def close(self):
        '''
        Disconnect from the server and close the socket
        '''
        self.__disconnect()
        ClientDuplexer.close(self)
