from client_duplexer import ClientDuplexer
from socket import socket, AF_INET, SOCK_DGRAM

class client(ClientDuplexer):

    def __init__(self, addr: str, port: int):
        client = socket(AF_INET, SOCK_DGRAM)
        client.connect((addr, port))
        ClientDuplexer.__init__(self, client, True)


client1 = client('127.0.0.1', 13370)
client1.send('CONNECT 5 24524284702934701298465203984762098562093460924615987240598')
print(client1.read())
input('press enter to continue...')
