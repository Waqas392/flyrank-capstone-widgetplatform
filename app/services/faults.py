"""Runtime fault switches so failure paths can be proven deterministically (dev only)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Faults:
    geo_down: set[str] = field(default_factory=set)  # subset of {"a", "b"}
    email_fail: bool = False

    def snapshot(self) -> dict:
        return {"geo_down": sorted(self.geo_down), "email_fail": self.email_fail}
