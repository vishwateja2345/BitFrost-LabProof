"""Finite replay tool surface. There is deliberately no network executor."""
from dataclasses import dataclass
from enum import StrEnum
import time
from typing import Callable


class PolicyError(ValueError):
    pass


class Check(StrEnum):
    AUTHORIZATION = "object_authorization"
    REFLECTION = "html_reflection"
    DISCLOSURE = "error_disclosure"


@dataclass(frozen=True)
class Action:
    check_id: Check
    actor_id: str
    control: str

    @classmethod
    def parse(cls, value: dict) -> "Action":
        if not isinstance(value, dict) or set(value) != {"check_id", "actor_id", "control"}:
            raise PolicyError("Only check_id, actor_id and control are permitted")
        if any(not isinstance(v, str) for v in value.values()):
            raise PolicyError("Tool fields must be strings")
        try:
            check = Check(value["check_id"])
        except ValueError as exc:
            raise PolicyError("Unknown catalogue check") from exc
        actor, control = value["actor_id"], value["control"]
        if actor not in {"alice", "bob"} or control not in {"probe", "normal"}:
            raise PolicyError("Unknown synthetic actor or control")
        expected_actor = "bob" if check == Check.AUTHORIZATION and control == "normal" else "alice"
        if actor != expected_actor:
            raise PolicyError("Actor not permitted for this catalogue operation")
        return cls(check, actor, control)

    def validate(self) -> None:
        self.parse(self.to_dict())

    def to_dict(self) -> dict:
        return {"check_id": str(self.check_id), "actor_id": self.actor_id, "control": self.control}


@dataclass(frozen=True)
class Limits:
    max_actions: int = 36
    max_response_bytes: int = 4096
    max_total_bytes: int = 65536
    max_seconds: float = 10.0
    concurrency: int = 1
    max_model_calls: int = 0

    def __post_init__(self):
        for name, ceiling in (("max_actions", 36), ("max_response_bytes", 4096), ("max_total_bytes", 65536)):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= ceiling:
                raise PolicyError(f"{name} exceeds fixed replay ceiling")
        # Native comparisons reject NaN/infinity and huge integers without float conversion.
        if type(self.max_seconds) not in {int, float} or not 0 < self.max_seconds <= 10:
            raise PolicyError("Invalid wall-time limit")
        if type(self.concurrency) is not int or self.concurrency != 1 or type(self.max_model_calls) is not int or self.max_model_calls != 0:
            raise PolicyError("Replay is serial and cannot call models")


class Budget:
    def __init__(self, limits: Limits, clock: Callable[[], float] = time.monotonic):
        self.limits, self.clock = limits, clock
        self.started = clock()
        self.actions = self.response_bytes = 0
        self.cancelled = False

    def check(self):
        if self.cancelled:
            raise PolicyError("cancelled")
        if self.clock() - self.started >= self.limits.max_seconds:
            raise PolicyError("wall_time_exhausted")

    def reserve(self):
        self.check()
        if self.actions >= self.limits.max_actions:
            raise PolicyError("action_budget_exhausted")
        self.actions += 1  # Failed attempts also consume the budget.

    def consume(self, byte_count: int):
        self.check()
        if byte_count > self.limits.max_response_bytes or self.response_bytes + byte_count > self.limits.max_total_bytes:
            raise PolicyError("response_byte_budget_exhausted")
        self.response_bytes += byte_count


CATALOGUE = tuple(Check)
VARIANTS = ("vulnerable", "corrected", "uncertain")
PHASES = ("observation", "verification")


def catalogue_actions():
    for check in CATALOGUE:
        for control in ("probe", "normal"):
            yield Action.parse({"check_id": check.value, "actor_id": "bob" if check == Check.AUTHORIZATION and control == "normal" else "alice", "control": control})
