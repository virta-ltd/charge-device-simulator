from enum import Enum


class Flows(Enum):
    Heartbeat = 'heartbeat'
    Authorize = 'authorize'
    Charge = 'charge'
    StatusPreparing = 'status_preparing'
