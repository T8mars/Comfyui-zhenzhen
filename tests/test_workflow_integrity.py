import json
import re
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = PLUGIN_ROOT / "workflow"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")


class WorkflowIntegrityTests(unittest.TestCase):
    def workflow_documents(self):
        for path in sorted(WORKFLOW_ROOT.rglob("*.json")):
            text = path.read_text(encoding="utf-8-sig")
            with self.subTest(path=path):
                self.assertIsNone(SECRET_PATTERN.search(text))
                yield path, json.loads(text)

    def test_all_workflows_parse_without_embedded_keys(self):
        documents = list(self.workflow_documents())
        self.assertGreater(len(documents), 0)

    def test_links_reference_existing_serialized_slots(self):
        failures = []
        for path, document in self.workflow_documents():
            nodes = {
                node.get("id"): node
                for node in document.get("nodes", [])
                if isinstance(node, dict) and "id" in node
            }
            for link in document.get("links", []):
                if not isinstance(link, list) or len(link) < 5:
                    failures.append((str(path), link, "invalid link record"))
                    continue
                link_id, source_id, source_slot, target_id, target_slot = link[:5]
                source = nodes.get(source_id)
                target = nodes.get(target_id)
                if source is None or target is None:
                    failures.append((str(path), link_id, "missing endpoint node"))
                    continue
                outputs = source.get("outputs") or []
                inputs = target.get("inputs") or []
                if not isinstance(source_slot, int) or not 0 <= source_slot < len(outputs):
                    failures.append((str(path), link_id, "source slot", source_slot, len(outputs)))
                if not isinstance(target_slot, int) or not 0 <= target_slot < len(inputs):
                    failures.append((str(path), link_id, "target slot", target_slot, len(inputs)))

        self.assertFalse(failures, failures[:20])

    def test_bundled_settings_nodes_use_final_unique_registration(self):
        primary_count = 0
        legacy = []
        for path, document in self.workflow_documents():
            for node in document.get("nodes", []):
                if node.get("type") == "T8Zhenzhen_API_Settings":
                    primary_count += 1
                elif node.get("type") in {"Zhenzhen_api_set", "Comfly_api_set"}:
                    legacy.append((str(path), node.get("id")))

        self.assertGreater(primary_count, 0)
        self.assertFalse(legacy, legacy)


if __name__ == "__main__":
    unittest.main()
