"""Configuration, loaded from environment variables.

Everything has a safe default so the project runs with zero setup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # "mock" keeps everything offline. "openai" / "anthropic" call a real model.
    provider: str = field(default_factory=lambda: os.getenv("DOC_TRIAGE_PROVIDER", "mock"))
    model: str = field(default_factory=lambda: os.getenv("DOC_TRIAGE_MODEL", "gpt-4o-mini"))

    # Routing thresholds. A field below `low` is treated as unreliable;
    # a document whose fields all clear `high` can auto-route.
    low_confidence_threshold: float = field(
        default_factory=lambda: _get_float("LOW_CONF_THRESHOLD", 0.60)
    )
    high_confidence_threshold: float = field(
        default_factory=lambda: _get_float("HIGH_CONF_THRESHOLD", 0.85)
    )


settings = Settings()
