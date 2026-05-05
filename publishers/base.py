from __future__ import annotations
from abc import ABC, abstractmethod


class ReportPublisher(ABC):
    """Publish a completed intelligence report to an external channel."""

    @abstractmethod
    async def publish(self, report: dict) -> None: ...
