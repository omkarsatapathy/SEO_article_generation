"""
config/config.py
================
Single config loader for the SEO article generation project.

Reads settings.yaml, hyperparams.yaml, and prompts.yaml from this
directory and exposes them as a unified ``cfg`` object with dot-notation
access (``cfg.settings.llm.model``, ``cfg.hyperparams.qa.pass_score``,
``cfg.prompts.tools.metadata``, etc.).

Usage
-----
    from config.config import cfg

    model_name = cfg.settings.llm.model
    max_retries = cfg.hyperparams.pipeline.max_retries
    prompt = cfg.prompts.tools.metadata.format(primary_keyword=..., preview=...)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_ns(obj: Any) -> Any:
    """Recursively convert dicts to SimpleNamespace for dot-notation access."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_ns(item) for item in obj]
    return obj


def _load(filename: str) -> SimpleNamespace:
    path = _CONFIG_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _to_ns(raw or {})


# ── Public config object ──────────────────────────────────────────────────────

class _Config:
    """Lazily-loaded, singleton-style configuration container."""

    def __init__(self) -> None:
        self._settings: SimpleNamespace | None = None
        self._hyperparams: SimpleNamespace | None = None
        self._prompts: SimpleNamespace | None = None

    @property
    def settings(self) -> SimpleNamespace:
        if self._settings is None:
            self._settings = _load("settings.yaml")
        return self._settings

    @property
    def hyperparams(self) -> SimpleNamespace:
        if self._hyperparams is None:
            self._hyperparams = _load("hyperparams.yaml")
        return self._hyperparams

    @property
    def prompts(self) -> SimpleNamespace:
        if self._prompts is None:
            self._prompts = _load("prompts.yaml")
        return self._prompts


cfg = _Config()
