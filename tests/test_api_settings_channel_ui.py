import ast
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def class_node(class_name):
    tree = ast.parse((PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def api_settings_input_types(class_name):
    node = class_node(class_name)
    method_node = next(
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "INPUT_TYPES"
    )
    return_node = next(item for item in ast.walk(method_node) if isinstance(item, ast.Return))
    return ast.literal_eval(return_node.value)


class ApiSettingsChannelUiTests(unittest.TestCase):
    def test_canonical_settings_has_only_zhenzhen_channels(self):
        api_base = api_settings_input_types(
            "T8Zhenzhen_API_Settings"
        )["required"]["api_base"]

        self.assertEqual(api_base[0], ["zhenzhen", "seedance_low_price", "ip"])
        self.assertEqual(api_base[1]["default"], "seedance_low_price")

    def test_both_legacy_classes_inherit_the_canonical_contract(self):
        for name in ("Zhenzhen_api_set", "Comfly_api_set"):
            with self.subTest(name=name):
                node = class_node(name)
                self.assertEqual(node.bases[0].id, "T8Zhenzhen_API_Settings")
                self.assertTrue(
                    any(
                        isinstance(item, ast.Assign)
                        and any(
                            isinstance(target, ast.Name) and target.id == "DEPRECATED"
                            for target in item.targets
                        )
                        for item in node.body
                    )
                )

    def test_frontend_migrates_only_zhenzhen_legacy_graph_nodes(self):
        source = (
            PLUGIN_ROOT / "web" / "js" / "api_settings_channel_ui.js"
        ).read_text(encoding="utf-8")

        self.assertIn('"T8Zhenzhen_API_Settings"', source)
        self.assertIn('"Zhenzhen_api_set"', source)
        self.assertIn('"Comfly_api_set"', source)
        self.assertIn("beforeConfigureGraph", source)
        self.assertIn("migrateLegacySettingsNodes(graphData)", source)
        self.assertIn('choices.has("seedance_low_price")', source)
        self.assertIn('!choices.has("comfly")', source)
        self.assertEqual(source.count('addWidget("button"'), 1)
        self.assertIn('label: "注册平价小屋 API ↗"', source)
        self.assertIn('url: "https://api.seedance.nz/sign-up?aff=5f4w"', source)
        self.assertIn('label: "注册 AI 工坊 API ↗"', source)
        self.assertIn('url: "https://ai.t8star.org/register?aff=dP7j"', source)


if __name__ == "__main__":
    unittest.main()
