import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


EXPECTED_IMAGE_MODELS = [
    "zhenzhen-image-nb-flash",
    "zhenzhen-image-nb-2",
    "zhenzhen-image-nb-2-lite",
    "zhenzhen-image-nb-pro",
]


class ZhenzhenImageGV2UXTests(unittest.TestCase):
    def test_size_is_a_combo_with_custom_wxh_support(self):
        inputs = nodes.Comfly_zhenzhen_image_g_v2_lowprice.INPUT_TYPES()
        self.assertEqual(
            inputs["required"]["size"][0],
            [
                "1:1",
                "16:9",
                "9:16",
                "21:9",
                "9:21",
                "4:3",
                "3:4",
                "3:2",
                "2:3",
                "4:5",
                "5:4",
                "custom",
            ],
        )
        self.assertEqual(
            inputs["optional"]["custom_size"],
            ("STRING", {"default": "1024x1024"}),
        )
        optional_names = list(inputs["optional"])
        self.assertLess(
            optional_names.index("skip_error"),
            optional_names.index("custom_size"),
        )

    def test_payload_supports_presets_custom_and_legacy_wxh(self):
        common = (
            nodes.ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL,
            "a clean editorial product photograph",
            "1k",
        )
        preset = nodes.build_zhenzhen_image_g_v2_payload(
            *common,
            "16:9",
            1,
        )
        custom = nodes.build_zhenzhen_image_g_v2_payload(
            *common,
            "custom",
            1,
            custom_size="1280X720",
        )
        legacy = nodes.build_zhenzhen_image_g_v2_payload(
            *common,
            "2048x1024",
            1,
        )
        self.assertEqual(preset["size"], "16:9")
        self.assertEqual(custom["size"], "1280x720")
        self.assertEqual(legacy["size"], "2048x1024")
        for common_size in ("21:9", "9:21", "4:3", "3:4", "4:5", "5:4"):
            with self.subTest(common_size=common_size):
                payload = nodes.build_zhenzhen_image_g_v2_payload(
                    *common,
                    common_size,
                    1,
                )
                self.assertEqual(payload["size"], common_size)

        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "custom_size"):
            nodes.build_zhenzhen_image_g_v2_payload(
                *common,
                "custom",
                1,
                custom_size="wide",
            )

    def test_workflows_use_capability_title_and_frontend_migration(self):
        paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "zhenzhen-image-g-v2-lowprice*（贞贞的平价AI小屋）.json"
            )
        )
        self.assertEqual(len(paths), 2)
        for path in paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
            workflow = json.loads(raw)
            node = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_zhenzhen_image_g_v2_lowprice"
            )
            self.assertEqual(node["title"], "Image G V2 图像生成/编辑")
            self.assertEqual(node["widgets_values"][3:], ["1:1", 1, False, "1024x1024"])

        dynamic_ui = (
            PLUGIN_ROOT / "web/js/zhenzhen_nb_v31_ui.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"Comfly_zhenzhen_image_g_v2_lowprice"', dynamic_ui)
        self.assertIn('widgetByName(node, "custom_size")', dynamic_ui)
        self.assertIn('sizeWidget.value = "custom"', dynamic_ui)


class ZhenzhenImageNBContractTests(unittest.TestCase):
    def test_catalog_and_domestic_config(self):
        self.assertEqual(nodes.ZHENZHEN_IMAGE_NB_MODELS, EXPECTED_IMAGE_MODELS)
        inputs = nodes.Comfly_zhenzhen_image_nb_lowprice.INPUT_TYPES()
        self.assertEqual(
            inputs["optional"]["api_config"][0],
            "ZHENZHEN_SEEDANCE2_CONFIG",
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("image")],
            [f"image{index}" for index in range(1, 15)],
        )

    def test_every_model_builds_documented_payload(self):
        cases = (
            (nodes.ZHENZHEN_IMAGE_NB_FLASH_MODEL, "1k", "auto", 1),
            (nodes.ZHENZHEN_IMAGE_NB_2_MODEL, "0.5k", "1:8", 1),
            (nodes.ZHENZHEN_IMAGE_NB_2_LITE_MODEL, "1k", "8:1", 4),
            (nodes.ZHENZHEN_IMAGE_NB_PRO_MODEL, "4k", "21:9", 1),
        )
        for model, resolution, size, count in cases:
            with self.subTest(model=model):
                payload = nodes.build_zhenzhen_image_nb_payload(
                    model,
                    "a clean editorial product photograph",
                    resolution,
                    size,
                    count,
                    ["https://example.test/a.png", "https://example.test/b.png"],
                )
                self.assertEqual(payload["model"], model)
                self.assertEqual(payload["n"], count)
                self.assertEqual(payload["size"], size)
                self.assertEqual(payload["metadata"], {"resolution": resolution})
                self.assertEqual(len(payload["images"]), 2)

    def test_text_payload_omits_images(self):
        payload = nodes.build_zhenzhen_image_nb_payload(
            nodes.ZHENZHEN_IMAGE_NB_PRO_MODEL,
            "a clean editorial product photograph",
            "1k",
            "1:1",
            1,
        )
        self.assertNotIn("images", payload)

    def test_model_specific_validation(self):
        invalid_cases = (
            (
                nodes.ZHENZHEN_IMAGE_NB_FLASH_MODEL,
                "x" * 1001,
                "1k",
                "1:1",
                1,
                "1000",
            ),
            (
                nodes.ZHENZHEN_IMAGE_NB_FLASH_MODEL,
                "valid prompt",
                "2k",
                "1:1",
                1,
                "resolution",
            ),
            (
                nodes.ZHENZHEN_IMAGE_NB_PRO_MODEL,
                "valid prompt",
                "1k",
                "1:8",
                1,
                "size",
            ),
            (
                nodes.ZHENZHEN_IMAGE_NB_2_MODEL,
                "valid prompt",
                "1k",
                "1:1",
                2,
                " n ",
            ),
        )
        for model, prompt, resolution, size, count, message in invalid_cases:
            with self.subTest(model=model, message=message):
                with self.assertRaisesRegex(nodes.SeedanceLowPriceError, message):
                    nodes.build_zhenzhen_image_nb_payload(
                        model, prompt, resolution, size, count
                    )

    def test_execute_uploads_reference_and_returns_image(self):
        expected = torch.zeros((1, 4, 4, 3), dtype=torch.float32)
        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://example.test/result.png",
            }
        }
        with (
            patch.object(
                nodes,
                "resolve_config",
                return_value={"base_url": "https://api.seedance.nz", "api_key": "test"},
            ),
            patch.object(
                nodes,
                "_upload_image_slots",
                return_value=["https://example.test/input.png"],
            ) as upload,
            patch.object(
                nodes,
                "submit_image_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_image_task", return_value=final),
            patch.object(nodes, "download_image", return_value=expected),
        ):
            result = nodes.Comfly_zhenzhen_image_nb_lowprice().generate_image(
                model=nodes.ZHENZHEN_IMAGE_NB_PRO_MODEL,
                prompt="keep the product, replace the background",
                resolution="1k",
                size="1:1",
                n=1,
                image1=torch.zeros((1, 8, 8, 3), dtype=torch.float32),
            )
        upload.assert_called_once()
        self.assertEqual(submit.call_args.args[0]["images"], ["https://example.test/input.png"])
        self.assertIs(result[0], expected)


class ZhenzhenVideoV31LiteTests(unittest.TestCase):
    def test_lite_is_in_existing_v31_node(self):
        self.assertEqual(
            nodes.ZHENZHEN_VIDEO_V31_MODELS,
            [
                "zhenzhen-video-v31-fast",
                "zhenzhen-video-v31-quality",
                "zhenzhen-video-v31-lite",
            ],
        )
        choices = nodes.Comfly_zhenzhen_video_v31_lowprice.INPUT_TYPES()[
            "required"
        ]["model"][0]
        self.assertEqual(choices, nodes.ZHENZHEN_VIDEO_V31_MODELS)

    def test_lite_payload_is_text_only(self):
        payload = nodes.build_zhenzhen_video_v31_payload(
            nodes.ZHENZHEN_VIDEO_V31_LITE_MODEL,
            "a paper airplane gliding through sunrise clouds",
            "720p",
            "16:9",
        )
        self.assertEqual(payload["seconds"], "8")
        self.assertNotIn("images", payload)
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "text-to-video only"):
            nodes.build_zhenzhen_video_v31_payload(
                nodes.ZHENZHEN_VIDEO_V31_LITE_MODEL,
                "a paper airplane gliding through sunrise clouds",
                "720p",
                "16:9",
                ["https://example.test/start.png"],
            )

    def test_fast_and_quality_regression(self):
        fast = nodes.build_zhenzhen_video_v31_payload(
            nodes.ZHENZHEN_VIDEO_V31_FAST_MODEL,
            "cinematic ocean waves",
            "720p",
            "16:9",
            ["a", "b", "c"],
        )
        self.assertEqual(fast["images"], ["a", "b", "c"])
        quality = nodes.build_zhenzhen_video_v31_payload(
            nodes.ZHENZHEN_VIDEO_V31_QUALITY_MODEL,
            "cinematic ocean waves",
            "1080p",
            "9:16",
            ["a", "b"],
        )
        self.assertEqual(quality["images"], ["a", "b"])
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "Quality"):
            nodes.build_zhenzhen_video_v31_payload(
                nodes.ZHENZHEN_VIDEO_V31_QUALITY_MODEL,
                "cinematic ocean waves",
                "720p",
                "16:9",
                ["a", "b", "c"],
            )


class ZhenzhenNBWorkflowTests(unittest.TestCase):
    def test_workflows_cover_every_supported_mode_without_secrets(self):
        image_paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "zhenzhen-image-nb-*（贞贞的平价AI小屋）.json"
            )
        )
        self.assertEqual(len(image_paths), 8)
        covered = set()
        for path in image_paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
            workflow = json.loads(raw)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"][0], "seedance_low_price")
            self.assertEqual(settings["widgets_values"][1], "")
            node = next(node for node in workflow["nodes"] if node["type"] == "Comfly_zhenzhen_image_nb_lowprice")
            model = node["widgets_values"][0]
            editing = "图像编辑" in path.name
            covered.add((model, editing))
            image1 = next(value for value in node["inputs"] if value["name"] == "image1")
            self.assertEqual(image1["link"] is not None, editing)
        self.assertEqual(
            covered,
            {(model, editing) for model in EXPECTED_IMAGE_MODELS for editing in (False, True)},
        )

    def test_lite_workflow_and_frontend_registration(self):
        path = PLUGIN_ROOT / "workflow" / "zhenzhen-video-v31-lite文生视频（贞贞的平价AI小屋）.json"
        workflow = json.loads(path.read_text(encoding="utf-8"))
        node = next(node for node in workflow["nodes"] if node["type"] == "Comfly_zhenzhen_video_v31_lowprice")
        self.assertEqual(node["widgets_values"][:5], ["zhenzhen-video-v31-lite", "一架纸飞机穿过日出时分的暖色云层，流畅的电影感镜头运动", "8", "720p", "16:9"])
        self.assertFalse(any(value["link"] for value in node["inputs"] if value["name"].startswith("image")))

        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        dynamic_ui = (PLUGIN_ROOT / "web/js/zhenzhen_nb_v31_ui.js").read_text(encoding="utf-8")
        self.assertIn('"Comfly_zhenzhen_image_nb_lowprice"', comfly)
        self.assertIn('"Comfly_zhenzhen_image_nb_lowprice"', api_link)
        for model in EXPECTED_IMAGE_MODELS:
            self.assertIn(f'"{model}"', dynamic_ui)
        self.assertIn('model !== "zhenzhen-video-v31-lite"', dynamic_ui)


if __name__ == "__main__":
    unittest.main()
