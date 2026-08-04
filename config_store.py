"""Compatibility shims for the retired project-level API key store.

API keys belong to ComfyUI workflow widgets. These functions intentionally do
not read, write, or create ``Comflyapi.json``; they remain only so older node
implementations can keep calling the same helpers without persisting secrets.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict


CONFIG_PATH = Path(__file__).resolve().parent / "Comflyapi.json"
CONFIG_LOCK = threading.RLock()


class ProjectConfigError(RuntimeError):
    pass


def get_project_config_lock() -> threading.RLock:
    return CONFIG_LOCK


def read_project_config(strict: bool = False) -> Dict[str, Any]:
    del strict
    return {}


def write_project_config(config: Dict[str, Any], merge: bool = True) -> None:
    if not isinstance(config, dict):
        raise TypeError("Project configuration must be a dictionary.")
    del config, merge
