"""Data freshness tracker — singleton registry for collector health."""

import time
from dataclasses import dataclass
from typing import Optional


# Expected poll intervals per source (seconds) — used for staleness classification
_INTERVALS: dict[str, float] = {}


@dataclass
class SourceStatus:
    name: str
    last_success: float = 0.0
    last_error: float = 0.0
    last_error_msg: str = ""
    collect_count: int = 0
    error_count: int = 0

    @property
    def age_seconds(self) -> float:
        if self.last_success == 0:
            return float("inf")
        return time.time() - self.last_success

    @property
    def status(self) -> str:
        age = self.age_seconds
        if age == float("inf"):
            if self.last_error > 0:
                return "error"
            return "no_data"
        # Stale after 2x expected interval, down after 8x
        threshold = _INTERVALS.get(self.name, 600)
        if age < threshold:
            return "fresh"
        if age < threshold * 4:
            return "stale"
        return "down"


class DataFreshnessTracker:
    """Singleton tracker for all data source health."""

    _instance: Optional["DataFreshnessTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sources: dict[str, SourceStatus] = {}
        return cls._instance

    def register(self, name: str, interval: float):
        """Register a source with its expected poll interval."""
        _INTERVALS[name] = interval * 2  # stale after 2x interval
        if name not in self._sources:
            self._sources[name] = SourceStatus(name=name)

    def report_success(self, name: str):
        src = self._sources.get(name)
        if src:
            src.last_success = time.time()
            src.collect_count += 1
            src.last_error_msg = ""

    def report_error(self, name: str, error: str):
        src = self._sources.get(name)
        if src:
            src.last_error = time.time()
            src.last_error_msg = str(error)[:200]
            src.error_count += 1

    def snapshot(self) -> dict:
        """Return JSON-serializable health snapshot."""
        result = {}
        for name, src in self._sources.items():
            age = src.age_seconds
            result[name] = {
                "status": src.status,
                "last_success_ago": round(age, 1) if age != float("inf") else None,
                "last_error_msg": src.last_error_msg or None,
                "collect_count": src.collect_count,
                "error_count": src.error_count,
            }
        return result


# Module-level convenience
tracker = DataFreshnessTracker()
