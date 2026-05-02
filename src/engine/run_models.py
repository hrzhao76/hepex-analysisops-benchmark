from __future__ import annotations

from typing import Any

from pydantic import BaseModel, HttpUrl


class EvalRequest(BaseModel):
    participants: dict[str, HttpUrl]
    config: dict[str, Any]
    solver_backend: str | None = None
