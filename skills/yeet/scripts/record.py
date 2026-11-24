"""Schema for yeet records. Copy to `.yeet/record.py`; records import `Record` from it."""
from typing import Literal, TypedDict


class Record(TypedDict):
    kind: Literal["spec", "state", "handoff", "archive", "doc"]
    id: str
    prev: str | None
    next: str | None
    body: dict[str, object]
