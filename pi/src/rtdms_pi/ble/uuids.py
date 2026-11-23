"""The only UUID definitions for the Pi link."""

from enum import IntEnum

from dms_physiology.garmin_rr import CHARACTERISTIC_UUID as GARMIN_CHAR_UUID
from dms_physiology.garmin_rr import SERVICE_UUID as SERVICE_UUID

__all__ = ["SERVICE_UUID", "GARMIN_CHAR_UUID", "Char", "phone_uuid"]


class Char(IntEnum):
    ALERT = 1
    STATUS = 2
    PHYSIO = 3
    SETTINGS = 4
    COMMAND = 5
    RESULT = 6
    INCIDENT = 7
    CLOCK = 8
    AUTH = 9
    HEALTH = 10
    WATCH_ALERT = 11  # 0b: 2 raw bytes for the Garmin watch, not JSON (contract v1.3)

    @property
    def uuid(self) -> str:
        return phone_uuid(self)


def phone_uuid(nn: int) -> str:
    if not 1 <= nn <= 11:
        raise ValueError("unknown phone characteristic")
    return "1375193a-7edb-4a34-b3f2-18130239" + f"{nn:04x}"
