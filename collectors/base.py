"""Abstract base collector for all data sources."""

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    def __init__(self, name: str, interval: int):
        self.name = name
        self.interval = interval
        self._running = False

    @abstractmethod
    async def collect(self) -> list | dict:
        """Collect data from the source. Must be implemented by subclasses."""
        ...

    async def run(self):
        """Main loop: collect, handle errors, sleep."""
        self._running = True
        logger.info(f"[{self.name}] collector started (interval={self.interval}s)")
        while self._running:
            try:
                await self.collect()
            except Exception as e:
                logger.error(f"[{self.name}] collection error: {e}")
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False
