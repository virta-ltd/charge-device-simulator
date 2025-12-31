from enum import Enum


class ErrorReasons(Enum):
    InvalidResponse = 'invalid-response'
    ConnectionError = 'connection-error'
    UnknownException = 'unknown-exception'
