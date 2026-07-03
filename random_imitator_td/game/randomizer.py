from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import random
from typing import Any


@dataclass
class RngRoll:
    roll_index: int
    tick: int
    rng_stream: str
    purpose: str
    pool: list[str]
    base_weights: dict[str, int]
    adjusted_weights: dict[str, int]
    selected: str
    context: dict[str, Any]


class ReplayRng:
    def __init__(self, seed: str) -> None:
        self.seed = seed
        self._streams: dict[str, random.Random] = {}
        self.rolls: list[RngRoll] = []

    def _stream(self, rng_stream: str) -> random.Random:
        if rng_stream not in self._streams:
            digest = hashlib.sha256(f"{self.seed}:{rng_stream}".encode("utf-8")).digest()
            stream_seed = int.from_bytes(digest[:8], "big")
            self._streams[rng_stream] = random.Random(stream_seed)
        return self._streams[rng_stream]

    def roll(
        self,
        rng_stream: str,
        purpose: str,
        pool: list[str],
        base_weights: dict[str, int],
        context: dict[str, Any] | None = None,
        *,
        adjusted_weights: dict[str, int] | None = None,
        tick: int = 0,
    ) -> str:
        if not pool:
            raise ValueError("pool must not be empty")
        weights = adjusted_weights or base_weights
        missing = [item for item in pool if item not in weights]
        if missing:
            raise ValueError(f"missing weights for: {missing}")
        if any(weights[item] < 0 for item in pool):
            raise ValueError("weights must not be negative")
        if sum(weights[item] for item in pool) <= 0:
            raise ValueError("total weight must be greater than zero")
        selected = self._stream(rng_stream).choices(
            population=pool,
            weights=[weights[item] for item in pool],
            k=1,
        )[0]
        self.rolls.append(
            RngRoll(
                roll_index=len(self.rolls),
                tick=tick,
                rng_stream=rng_stream,
                purpose=purpose,
                pool=list(pool),
                base_weights=dict(base_weights),
                adjusted_weights=dict(weights),
                selected=selected,
                context=dict(context or {}),
            )
        )
        return selected

    def snapshot(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "streams": {
                name: _state_to_json(stream.getstate())
                for name, stream in self._streams.items()
            },
            "rolls": [asdict(roll) for roll in self.rolls],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "ReplayRng":
        rng = cls(str(snapshot.get("seed", "")))
        rng.rolls = [RngRoll(**roll) for roll in snapshot.get("rolls", [])]
        for name, state in snapshot.get("streams", {}).items():
            stream = random.Random()
            stream.setstate(_state_from_json(state))
            rng._streams[str(name)] = stream
        return rng


def _state_to_json(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_state_to_json(item) for item in value]
    if isinstance(value, list):
        return [_state_to_json(item) for item in value]
    return value


def _state_from_json(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_state_from_json(item) for item in value)
    return value
