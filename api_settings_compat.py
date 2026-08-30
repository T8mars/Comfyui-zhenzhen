"""Registration helpers for API Settings compatibility aliases."""

from __future__ import annotations

from types import ModuleType
from typing import Any


PRIMARY_SETTINGS_KEY = "T8Zhenzhen_API_Settings"
PRIMARY_DISPLAY_NAME = "Zhenzhen API Settings"
INTERMEDIATE_SETTINGS_KEY = "Zhenzhen_api_set"
LEGACY_SETTINGS_KEY = "Comfly_api_set"
LEGACY_DISPLAY_NAME = "Zhenzhen API Settings (Legacy)"
_COMFLY_CHANNELS = frozenset({"comfly", "ip", "hk", "us"})


def _api_base_choices(node_class: type[Any]) -> set[str]:
    if not isinstance(node_class, type):
        return set()
    try:
        definition = node_class.INPUT_TYPES()["required"]["api_base"]
        choices = definition[0]
    except Exception:
        return set()
    if not isinstance(choices, (list, tuple)):
        return set()
    return {str(choice) for choice in choices}


def _is_external_comfly_settings_class(
    node_class: type[Any] | None,
    zhenzhen_settings_class: type[Any],
) -> bool:
    if node_class is None or node_class is zhenzhen_settings_class:
        return False
    return _COMFLY_CHANNELS.issubset(_api_base_choices(node_class))


def avoid_legacy_registration_collision(
    node_class_mappings: dict[str, type[Any]],
    display_name_mappings: dict[str, str],
    comfy_nodes: ModuleType | Any | None = None,
) -> bool:
    """Do not export our shared legacy alias when Comfyui_Comfly owns it.

    The canonical and intermediate Zhenzhen ids remain registered. Old
    Zhenzhen UI workflows are migrated to the canonical id by the frontend
    extension before the graph is configured.
    """

    if comfy_nodes is None:
        try:
            import nodes as comfy_nodes  # type: ignore[no-redef]
        except (ImportError, AttributeError):
            return False

    global_mappings = getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", None)
    if not isinstance(global_mappings, dict):
        return False

    existing = global_mappings.get(LEGACY_SETTINGS_KEY)
    own_legacy_class = node_class_mappings.get(LEGACY_SETTINGS_KEY)
    if not _is_external_comfly_settings_class(existing, own_legacy_class):
        return False

    node_class_mappings.pop(LEGACY_SETTINGS_KEY, None)
    display_name_mappings.pop(LEGACY_SETTINGS_KEY, None)
    return True
