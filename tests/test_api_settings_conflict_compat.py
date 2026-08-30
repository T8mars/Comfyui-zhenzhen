import json
import types
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(PLUGIN_ROOT))

from api_settings_compat import (  # noqa: E402
    INTERMEDIATE_SETTINGS_KEY,
    LEGACY_SETTINGS_KEY,
    PRIMARY_SETTINGS_KEY,
    avoid_legacy_registration_collision,
)


class _ZhenzhenLegacySettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_base": (["zhenzhen", "seedance_low_price", "ip"],),
            }
        }


class _ExternalComflySettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_base": (["comfly", "ip", "hk", "us"],),
            }
        }


class ApiSettingsConflictCompatTests(unittest.TestCase):
    def local_mappings(self):
        return {
            PRIMARY_SETTINGS_KEY: _ZhenzhenLegacySettings,
            INTERMEDIATE_SETTINGS_KEY: _ZhenzhenLegacySettings,
            LEGACY_SETTINGS_KEY: _ZhenzhenLegacySettings,
        }

    def test_external_owner_is_not_overwritten_when_it_loaded_first(self):
        local_mappings = self.local_mappings()
        display_mappings = {key: key for key in local_mappings}
        fake_nodes = types.SimpleNamespace(
            NODE_CLASS_MAPPINGS={LEGACY_SETTINGS_KEY: _ExternalComflySettings},
        )

        removed = avoid_legacy_registration_collision(
            local_mappings,
            display_mappings,
            fake_nodes,
        )

        self.assertTrue(removed)
        self.assertNotIn(LEGACY_SETTINGS_KEY, local_mappings)
        self.assertNotIn(LEGACY_SETTINGS_KEY, display_mappings)
        self.assertIn(PRIMARY_SETTINGS_KEY, local_mappings)
        self.assertIn(INTERMEDIATE_SETTINGS_KEY, local_mappings)
        self.assertIs(
            fake_nodes.NODE_CLASS_MAPPINGS[LEGACY_SETTINGS_KEY],
            _ExternalComflySettings,
        )

    def test_legacy_alias_remains_when_no_external_owner_is_loaded(self):
        local_mappings = self.local_mappings()
        display_mappings = {key: key for key in local_mappings}
        fake_nodes = types.SimpleNamespace(NODE_CLASS_MAPPINGS={})

        removed = avoid_legacy_registration_collision(
            local_mappings,
            display_mappings,
            fake_nodes,
        )

        self.assertFalse(removed)
        self.assertIs(
            local_mappings[LEGACY_SETTINGS_KEY],
            _ZhenzhenLegacySettings,
        )

    def test_bundled_workflows_use_the_final_unique_id(self):
        old_nodes = []
        primary = 0
        for path in (PLUGIN_ROOT / "workflow").rglob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            for node in document.get("nodes", []):
                if node.get("type") in {
                    LEGACY_SETTINGS_KEY,
                    INTERMEDIATE_SETTINGS_KEY,
                }:
                    old_nodes.append((str(path), node.get("id")))
                if node.get("type") == PRIMARY_SETTINGS_KEY:
                    primary += 1

        self.assertFalse(old_nodes, old_nodes)
        self.assertGreater(primary, 0)


if __name__ == "__main__":
    unittest.main()
