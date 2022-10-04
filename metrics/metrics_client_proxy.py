import datetime
import platform
import hashlib

from .duplexer import Duplexer
# from duplexer import Duplexer # for testing

from socket import socket

class MetricsProxy(Duplexer):
    '''
    ClientProxy is a class that takes a socket as a parameter and sends information to the server
    '''
    __slots__ = ['client', 'interval', '__UUID']


    def __init__(self, socket: socket, interval: int):
        self.client = socket
        self.interval = interval
        self.__UUID = hashlib.sha256(f'{platform.machine()}:{platform.processor()}:{platform.system()}:{platform.node()}'.encode()).hexdigest()
        Duplexer.__init__(self, socket)
        self.connect()


    def repos_cloned(self, number: int):
        self.send(f'CLONED {number}')

    
    def clone_time(self, seconds: float):
        self.send(f'CLONETIME {seconds}')


    def files_added(self, number: int):
        self.send(f'ADD {number}')


    def add_time(self, seconds: float):
        self.send(f'ADDTIME {seconds}')


    def error_handled(self):
        self.send('ERROR')


    def students_accepted(self, number: int):
        month = datetime.datetime.now().strftime("%B").lower()
        self.send(f'ACCEPTED {month} {number}')


    def connect(self):
        self.send(f'CONNECT {self.interval} {self.__UUID}')


    def keep_alive(self):
        self.send(f'KEEPALIVE {self.__UUID}')
        

    def __disconnect(self):
        self.send(f'DISCONNECT {self.__UUID}')


    def close(self):
        '''
        Disconnect from the server and close the socket
        '''
        self.__disconnect()
        Duplexer.close(self)
