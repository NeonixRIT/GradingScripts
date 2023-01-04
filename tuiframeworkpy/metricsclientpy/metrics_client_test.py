from client_duplexer import ClientDuplexer

import socket


def main():
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.connect(('127.0.0.1', 13370))
        con = ClientDuplexer(client, False)
        con.send('CONNECT TEST TEST TEST')
        con.send('REQUEST')
        print(con.read())
    except KeyboardInterrupt:
        client.quit()


if __name__ == '__main__':
    main()
