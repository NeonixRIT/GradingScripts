import hashlib
import itertools
import platform

from typing import Any
from socket import socket

class ServerDuplexer:
    '''
    Class takes a udp socket as a parameter.
        read method to read incoming info from a socket,
        send method to send a message with a socket,
        close method to close a socket
    '''
    def __init__(self, socket: socket):
        self.socket = socket
        self.uuid = hashlib.sha256(f'{platform.machine()}:{platform.processor()}:{platform.system()}:{platform.node()}'.encode()).hexdigest()


    def read(self, encrypted: bool = False) -> tuple[str, Any]:
        message, addr = self.socket.recvfrom(1024)
        if encrypted:
            return self.__decrypt(message), addr
        return message.decode(), addr


    def send(self, message: str, addr, encrypt: bool = False):
        if encrypt:
            message = self.__encrypt(message)
            self.socket.sendto(message, addr)
        else:
            self.socket.sendto(message.encode(), addr)


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
                result += bytearray(a ^ b for a, b in zip(*map(bytearray, [segment, key.encode()])))
                message = message[len(key):]
            return result
        else:
            message = message.encode()
            key = key.encode()
            return bytearray(a ^ b for a, b in zip(*map(bytearray, [message, key])))


    def __decrypt(self, message: bytearray) -> str:
        key = self.uuid.encode()
        result = bytearray()
        if len(message) > len(key):
            while len(message) > 0:
                segment = message[:len(key)]
                if len(segment) < len(key):
                    segment = segment + '\r\n'.encode() * (len(key) - len(segment))
                result += bytearray(a ^ b for a, b in zip(*map(bytearray, [segment, key])))
                message = message[len(key):]
            return result.decode().strip()
        return bytearray(a ^ b for a, b in zip(*map(bytearray, [message, key]))).decode()
