from socket import socket

EOF = '\r\n\r\n'

class Duplexer:
    '''
    Class takes a udp socket as a parameter. 
        read method to read incoming info from a socket, 
        send method to send a message with a socket,
        close method to close a socket
    '''
    def __init__(self, socket: socket):
        self.socket = socket


    def read(self) -> str:
        return self.socket.recv(1024).decode()


    def send(self, message: str):
        self.socket.send(f'{message}{EOF}'.encode())


    def close(self):
        self.socket.close()
