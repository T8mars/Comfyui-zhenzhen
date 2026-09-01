import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {"base_url": "https://example.test", "api_key": "test-key"}


class SeedreamLayerDecompositionContractTests(unittest.TestCase):
    def test_node_uses_list_outputs_and_disables_single_image_concurrency(self):
        node = nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice
        self.assertEqual(
            node.RETURN_TYPES,
            ("IMAGE", "MASK", "STRING", "INT", "STRING", "STRING"),
        )
        self.assertEqual(
            node.OUTPUT_IS_LIST,
            (True, True, False, False, False, False),
        )
        self.assertTrue(node.COMFLY_CONCURRENT_DISABLED)
        inputs = node.INPUT_TYPES()["optional"]
        self.assertEqual(
            list(inputs), ["api_config", "skip_error", "seed", "model"]
        )
        self.assertTrue(inputs["seed"][1]["control_after_generate"])
        self.assertEqual(
            inputs["model"][0],
            [
                "seedream-v5-pro-layer-decomposition",
                "dola-seedream-5.0-pro-layer-decomposition",
            ],
        )
        self.assertEqual(
            inputs["model"][1]["default"],
            "seedream-v5-pro-layer-decomposition",
        )
        comfly_source = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        frontend_source = (
            PLUGIN_ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"Comfly_seedream_v5_pro_layer_decomposition_lowprice": '
            "Comfly_seedream_v5_pro_layer_decomposition_lowprice",
            comfly_source,
        )
        self.assertIn(
            '"Comfly_seedream_v5_pro_layer_decomposition_lowprice"',
            frontend_source,
        )

    def test_payload_matches_documented_contract(self):
        node = nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice()
        self.assertEqual(
            node._build_payload(
                "https://cdn.test/source.png", "", "auto", "png"
            ),
            {
                "model": "seedream-v5-pro-layer-decomposition",
                "images": ["https://cdn.test/source.png"],
                "metadata": {"resolution": "auto", "output_format": "png"},
            },
        )
        prompted = node._build_payload(
            "https://cdn.test/source.png", "separate the title", "1.5k", "jpeg"
        )
        self.assertEqual(prompted["prompt"], "separate the title")
        dola = node._build_payload(
            "https://cdn.test/source.png",
            "",
            "auto",
            "png",
            "dola-seedream-5.0-pro-layer-decomposition",
        )
        self.assertEqual(
            dola["model"], "dola-seedream-5.0-pro-layer-decomposition"
        )

    def test_validation_accepts_optional_prompt_and_rejects_image_batches(self):
        for resolution in ("auto", "1k", "1.5k", "2k"):
            with self.subTest(resolution=resolution):
                self.assertIs(
                    nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice.VALIDATE_INPUTS(
                        image=torch.zeros((1, 4, 4, 3)),
                        prompt="",
                        resolution=resolution,
                        output_format="png",
                        strict=True,
                    ),
                    True,
                )
        self.assertIsNot(
            nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice.VALIDATE_INPUTS(
                image=torch.zeros((2, 4, 4, 3)),
                prompt="",
                resolution="auto",
                output_format="png",
                strict=True,
            ),
            True,
        )
        self.assertIsNot(
            nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice.VALIDATE_INPUTS(
                image=torch.zeros((1, 4, 4, 3)),
                prompt="",
                resolution="auto",
                output_format="png",
                model="not-a-layer-model",
                strict=True,
            ),
            True,
        )

    def test_extract_image_urls_preserves_order_and_duplicates(self):
        urls = [
            "https://cdn.test/base.png",
            "https://cdn.test/layer.png",
            "https://cdn.test/layer.png",
        ]
        response = {
            "data": {
                "result_url": "https://cdn.test/summary.png",
                "data": {"content": {"image_urls": urls}},
            }
        }
        self.assertEqual(nodes.extract_image_urls(response), urls)

    def test_mask_is_inverse_alpha(self):
        rgba = Image.new("RGBA", (3, 2), (255, 0, 0, 255))
        rgba.putpixel((1, 0), (0, 255, 0, 0))
        with patch.object(
            nodes, "download_image_with_alpha_retry", return_value=rgba
        ):
            image, mask = nodes.download_image_with_mask(
                "https://cdn.test/layer.png"
            )
        self.assertEqual(tuple(image.shape), (1, 2, 3, 3))
        self.assertEqual(tuple(mask.shape), (1, 2, 3))
        self.assertEqual(float(mask[0, 0, 0]), 0.0)
        self.assertEqual(float(mask[0, 0, 1]), 1.0)

    def test_execute_downloads_every_result_without_resizing(self):
        node = nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice()
        urls = [
            "https://cdn.test/base.png",
            "https://cdn.test/layer-1.png",
            "https://cdn.test/layer-2.png",
        ]
        final_response = {
            "data": {
                "status": "SUCCESS",
                "data": {"content": {"image_urls": urls}},
            }
        }

        def fake_download(url):
            index = urls.index(url)
            image = torch.full((1, index + 2, index + 3, 3), float(index))
            mask = torch.full((1, index + 2, index + 3), float(index) / 2)
            return image, mask

        with patch.object(nodes, "resolve_config", return_value=CONFIG), patch.object(
            nodes, "upload_media", return_value="https://cdn.test/source.png"
        ), patch.object(
            nodes,
            "submit_image_task",
            return_value=("image-task", {"id": "image-task"}),
        ) as submit, patch.object(
            nodes, "poll_image_task", return_value=final_response
        ), patch.object(
            nodes, "download_image_with_mask", side_effect=fake_download
        ) as download:
            output = node.decompose_layers(
                image=torch.zeros((1, 8, 8, 3)),
                prompt="",
                resolution="auto",
                output_format="png",
            )

        self.assertNotIn("prompt", submit.call_args.args[0])
        self.assertEqual([call.args[0] for call in download.call_args_list], urls)
        images, masks, urls_json, count, task_id, response = output
        self.assertEqual(
            [tuple(item.shape) for item in images],
            [(1, 2, 3, 3), (1, 3, 4, 3), (1, 4, 5, 3)],
        )
        self.assertEqual(len(masks), 3)
        self.assertEqual(json.loads(urls_json), urls)
        self.assertEqual(count, 3)
        self.assertEqual(task_id, "image-task")
        self.assertEqual(json.loads(response)["result"], final_response)

    def test_skip_error_returns_type_safe_lists(self):
        node = nodes.Comfly_seedream_v5_pro_layer_decomposition_lowprice()
        images, masks, urls_json, count, task_id, response = node.decompose_layers(
            image=None,
            prompt="",
            resolution="auto",
            output_format="png",
            skip_error=True,
        )
        self.assertEqual(len(images), 1)
        self.assertEqual(tuple(images[0].shape), (1, 512, 512, 3))
        self.assertEqual(tuple(masks[0].shape), (1, 512, 512))
        self.assertEqual(urls_json, "[]")
        self.assertEqual(count, 0)
        self.assertEqual(task_id, "")
        self.assertEqual(json.loads(response)["status"], "error")

    def test_workflows_save_every_list_item_without_an_api_key(self):
        cases = {
            "zhenzhen-seedream-v5-pro图层拆分（贞贞的平价AI小屋）.json": (
                "seedream-v5-pro-layer-decomposition"
            ),
            "zhenzhen-dola-seedream-5.0-pro图层拆分（贞贞的平价AI小屋）.json": (
                "dola-seedream-5.0-pro-layer-decomposition"
            ),
        }
        for filename, expected_model in cases.items():
            with self.subTest(filename=filename):
                path = PLUGIN_ROOT / "workflow" / filename
                source = path.read_text(encoding="utf-8")
                workflow = json.loads(source)
                node_types = {node["type"] for node in workflow["nodes"]}
                self.assertIn(
                    "Comfly_seedream_v5_pro_layer_decomposition_lowprice",
                    node_types,
                )
                self.assertIn("JoinImageWithAlpha", node_types)
                self.assertIn("SaveImage", node_types)
                self.assertNotRegex(source, r"sk-[A-Za-z0-9_-]{12,}")
                config = next(
                    node
                    for node in workflow["nodes"]
                    if node["type"] == "Comfly_seedance2_low_price_settings"
                )
                self.assertEqual(config["widgets_values"][1], "")
                layer = next(
                    node
                    for node in workflow["nodes"]
                    if node["type"]
                    == "Comfly_seedream_v5_pro_layer_decomposition_lowprice"
                )
                self.assertEqual(layer["widgets_values"][6], expected_model)


if __name__ == "__main__":
    unittest.main()
