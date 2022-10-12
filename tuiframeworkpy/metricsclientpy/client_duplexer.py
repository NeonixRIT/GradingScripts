from socket import socket

import hashlib
import itertools
import platform

class ClientDuplexer:
    '''
    Class takes a udp socket as a parameter. 
        read method to read incoming info from a socket, 
        send method to send a message with a socket,
        close method to close a socket
    '''
    def __init__(self, socket: socket, encrypt: bool):
        self.socket = socket
        self.uuid = hashlib.sha256(f'{platform.machine()}:{platform.processor()}:{platform.system()}:{platform.node()}'.encode()).hexdigest()
        self.encrypt = encrypt


    def read(self) -> str:
        message = self.socket.recv(1024).decode()
        if self.encrypt:
            return self.__decrypt(message.encode())
        return message


    def send(self, message: str):
        if self.encrypt:
            message = self.__encrypt(message)
            self.socket.send(message)
        else:
            self.socket.send(message.encode())


    def close(self):
        self.socket.close()

    
    def __encrypt(self, message: str) -> bytearray:
        result = bytearray()
        key = self.uuid
        if len(message) > len(key):
            while len(message) > 0:
                segment = message[:len(key)].encode()
                if len(segment) < len(key):
                    segment = segment + '\r\n'.encode() * (len(key) - len(segment))
                result += bytearray(a^b for a, b in zip(*map(bytearray, [segment, key.encode()])))
                message = message[len(key):]
            return result
        else:
            message = message.encode()
            key = key.encode()
            return bytearray(a^b for a, b in zip(*map(bytearray, [message, key])))

        
    def __decrypt(self, message: bytearray) -> str:
        key = self.uuid.encode()
        result = bytearray()
        if len(message) > len(key):
            while len(message) > 0:
                segment = message[:len(key)]
                if len(segment) < len(key):
                    segment = segment + '\r\n'.encode() * (len(key) - len(segment))
                result += bytearray(a^b for a, b in zip(*map(bytearray, [segment, key])))
                message = message[len(key):]
            return result.decode().strip()
        return bytearray(a^b for a, b in zip(*map(bytearray, [message, key]))).decode()
