"""Shared test helpers: fixtures folder and instant (no real waiting) time."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


class FakeSleep:
    """Records requested sleeps instead of waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def fake_sleep() -> FakeSleep:
    return FakeSleep()
