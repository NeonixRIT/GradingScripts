import socket

def main():
    '''start UDP server that listens on port 127.0.0.1:1337 and prints out the data it receives'''
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('127.0.0.1', 1337))
    while True:
        data, addr = server.recvfrom(1024)
        print(f'[{addr}] {data.decode().strip()}')


main()
