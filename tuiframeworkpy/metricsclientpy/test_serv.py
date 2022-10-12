from server_duplexer import ServerDuplexer
from socket import socket, AF_INET, SOCK_DGRAM

class server(ServerDuplexer):
    
    def __init__(self, addr: str, port: int):
        server = socket(AF_INET, SOCK_DGRAM)
        server.bind((addr, port))
        ServerDuplexer.__init__(self, server)

    
    def run(self):
        while True:
            message, addr = self.read(encrypted=True)
            print(f'{message}')
            self.send('pong!', addr, encrypt=True)


server1 = server('127.0.0.1', 13370)
server1.run()