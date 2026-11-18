from dataclasses import dataclass
from enum import StrEnum

MAX_ACTOR_ID = 100
SYSTEM_ACTOR_ID = "system"


class Role(StrEnum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    COURIER = "COURIER"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class Actor:
    id: str
    role: Role
