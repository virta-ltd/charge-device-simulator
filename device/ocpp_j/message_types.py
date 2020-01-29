from enum import Enum


class MessageTypes(Enum):
    Req = 2
    Resp = 3
    RespError = 4
