"""Shared Suno model contract for the Zhenzhen AI Workshop nodes."""

from __future__ import annotations


SUNO_WORKSHOP_VERSION_OPTIONS = [
    "v3.0",
    "v3.5",
    "v4",
    "v4.5",
    "v4.5+",
    "v5",
    "v5.5",
    "v6",
    "v6 wild",
    "v6 mini",
]

SUNO_WORKSHOP_MV_BY_VERSION = {
    "v3.0": "chirp-v3.0",
    "v3.5": "chirp-v3.5",
    "v4": "chirp-v4",
    "v4.5": "chirp-auk",
    "v4.5+": "chirp-bluejay",
    "v5": "chirp-crow",
    "v5.5": "chirp-fenix",
    "v6": "chirp-hawk",
    "v6 wild": "chirp-hawk-wild",
    "v6 mini": "chirp-goose",
}

SUNO_WORKSHOP_V6_VERSIONS = frozenset(("v6", "v6 wild", "v6 mini"))
SUNO_WORKSHOP_V6_PROMPT_MAX = 5000
SUNO_WORKSHOP_V6_TAGS_MAX = 1000
SUNO_WORKSHOP_V6_MAX_DURATION_SECONDS = 8 * 60


def resolve_suno_workshop_mv(
    version: str,
    *,
    fallback: str,
    cover: bool = False,
) -> str:
    """Resolve the provider mv id while preserving legacy fallback behavior."""
    if cover and version == "v4":
        return "chirp-v4-tau"
    return SUNO_WORKSHOP_MV_BY_VERSION.get(version, fallback)


def validate_suno_workshop_text_limits(
    version: str,
    prompt: str,
    tags: str = "",
) -> None:
    """Apply the V6 prompt and style-tag limits published by the provider."""
    if version not in SUNO_WORKSHOP_V6_VERSIONS:
        return
    if len(prompt or "") > SUNO_WORKSHOP_V6_PROMPT_MAX:
        raise ValueError(
            f"Suno {version} prompt must not exceed "
            f"{SUNO_WORKSHOP_V6_PROMPT_MAX} characters"
        )
    if len(tags or "") > SUNO_WORKSHOP_V6_TAGS_MAX:
        raise ValueError(
            f"Suno {version} tags must not exceed "
            f"{SUNO_WORKSHOP_V6_TAGS_MAX} characters"
        )
