import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


class HailuoH3ContractTests(unittest.TestCase):
    def test_catalog_and_inputs_match_documentation(self):
        self.assertEqual(
            nodes.HAILUO_H3_MODELS,
            [
                "hailuo-h3-t2v",
                "hailuo-h3-i2v",
                "hailuo-h3-multi",
                "hailuo-h3-global-t2v",
                "hailuo-h3-global-i2v",
                "hailuo-h3-global-multi",
            ],
        )
        self.assertEqual(nodes.HAILUO_H3_SECONDS, [str(value) for value in range(5, 16)])
        self.assertEqual(nodes.HAILUO_H3_RESOLUTIONS, ["768P", "2K"])

        inputs = nodes.Comfly_hailuo_h3_video_lowprice.INPUT_TYPES()
        self.assertEqual(inputs["required"]["resolution"][1]["default"], "768P")
        self.assertEqual(
            inputs["optional"]["api_config"][0],
            "ZHENZHEN_SEEDANCE2_CONFIG",
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("image")],
            [f"image{index}" for index in range(1, 10)],
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("video")],
            [f"video{index}" for index in range(1, 4)],
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("audio")],
            [f"audio{index}" for index in range(1, 4)],
        )

    def test_text_to_video_payload(self):
        payload = nodes.build_hailuo_h3_payload(
            "hailuo-h3-t2v",
            "a camera glides through a rain-lit city street",
            "5",
            "768P",
            "21:9",
        )

        global_payload = nodes.build_hailuo_h3_payload(
            "hailuo-h3-global-t2v",
            "a camera glides through a rain-lit city street",
            "5",
            "768P",
            "21:9",
        )
        self.assertEqual(global_payload["model"], "hailuo-h3-global-t2v")
        self.assertEqual(
            global_payload["metadata"],
            {"resolution": "768P", "ratio": "21:9"},
        )
        self.assertEqual(
            payload,
            {
                "model": "hailuo-h3-t2v",
                "prompt": "a camera glides through a rain-lit city street",
                "seconds": "5",
                "metadata": {
                    "resolution": "768P",
                    "ratio": "21:9",
                },
            },
        )

    def test_image_to_video_payload_uses_first_and_last_frame(self):
        payload = nodes.build_hailuo_h3_payload(
            "hailuo-h3-global-i2v",
            "keep the subject consistent",
            "8",
            "2K",
            "16:9",
            [
                "https://example.test/first.png",
                "https://example.test/last.png",
            ],
        )
        self.assertEqual(
            payload,
            {
                "model": "hailuo-h3-global-i2v",
                "prompt": "keep the subject consistent",
                "seconds": "8",
                "metadata": {"resolution": "2K"},
                "images": [
                    "https://example.test/first.png",
                    "https://example.test/last.png",
                ],
            },
        )

    def test_multi_payload_maps_all_media_to_documented_fields(self):
        payload = nodes.build_hailuo_h3_payload(
            "hailuo-h3-global-multi",
            "match @Image 1, @Video 1 and @Audio 1",
            "15",
            "2K",
            "adaptive",
            ["https://example.test/image.png"],
            ["https://example.test/video.mp4"],
            ["https://example.test/audio.wav"],
        )
        self.assertEqual(payload["images"], ["https://example.test/image.png"])
        self.assertEqual(
            payload["metadata"],
            {
                "resolution": "2K",
                "ratio": "adaptive",
                "video_url": ["https://example.test/video.mp4"],
                "audio_url": ["https://example.test/audio.wav"],
            },
        )

    def test_model_specific_validation(self):
        cases = (
            ("hailuo-h3-t2v", "", "5", "2K", "16:9", "require a prompt"),
            ("hailuo-h3-multi", "", "5", "2K", "16:9", "require a prompt"),
            ("hailuo-h3-t2v", "valid", "4", "2K", "16:9", "between 5 and 15"),
            ("hailuo-h3-t2v", "valid", "5", "1080p", "16:9", "768P or 2K"),
        )
        for model, prompt, seconds, resolution, ratio, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(nodes.SeedanceLowPriceError, message):
                    nodes.build_hailuo_h3_payload(
                        model,
                        prompt,
                        seconds,
                        resolution,
                        ratio,
                    )

        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "requires image1"):
            nodes.build_hailuo_h3_payload(
                "hailuo-h3-global-i2v",
                "",
                "5",
                "2K",
                "16:9",
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "at least one"):
            nodes.build_hailuo_h3_payload(
                "hailuo-h3-global-multi",
                "valid",
                "5",
                "2K",
                "16:9",
            )

    def test_multi_execution_uploads_image_video_audio(self):
        final = {
            "status": "completed",
            "metadata": {"url": "https://example.test/result.mp4"},
        }

        def uploaded(_data, filename, _mime, _config):
            return f"https://example.test/{filename}"

        with (
            patch.object(
                nodes,
                "resolve_config",
                return_value={"base_url": "https://api.seedance.nz", "api_key": "test"},
            ),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(nodes, "video_to_mp4_bytes", return_value=b"mp4"),
            patch.object(nodes, "audio_to_wav_bytes", return_value=b"wav"),
            patch.object(nodes, "upload_media", side_effect=uploaded) as upload,
            patch.object(
                nodes,
                "submit_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_hailuo_h3_video_lowprice().generate(
                model="hailuo-h3-global-multi",
                prompt="match @Image 1, @Video 1 and @Audio 1",
                seconds="5",
                resolution="2K",
                ratio="16:9",
                image1=object(),
                video1=object(),
                audio1=object(),
            )

        self.assertEqual(upload.call_count, 3)
        payload = submit.call_args.args[0]
        self.assertEqual(
            payload["images"],
            ["https://example.test/hailuo_h3_image_1.png"],
        )
        self.assertEqual(
            payload["metadata"]["video_url"],
            ["https://example.test/hailuo_h3_video_1.mp4"],
        )
        self.assertEqual(
            payload["metadata"]["audio_url"],
            ["https://example.test/hailuo_h3_audio_1.wav"],
        )
        self.assertEqual(result[0], "downloaded-video")

    def test_existing_hailuo_23_payload_is_unchanged(self):
        payload = nodes.build_hailuo23_payload(
            "hailuo-2.3-t2v-standard",
            "cinematic ocean waves",
            "6",
            "768p",
            "16:9",
        )
        self.assertEqual(payload["model"], "hailuo-2.3-t2v-standard")
        self.assertEqual(payload["metadata"], {"resolution": "768p", "ratio": "16:9"})


class HailuoH3WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "zhenzhen-hailuo-h3*（贞贞的平价AI小屋）.json"
            )
        )

    def test_workflows_cover_all_models_without_secrets(self):
        self.assertEqual(len(self.paths), 6)
        covered = set()
        for path in self.paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
            self.assertNotIn("task_id\": \"", raw)
            workflow = json.loads(raw)
            settings = next(
                node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings"
            )
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            node = next(
                node
                for node in workflow["nodes"]
                if node["type"] == "Comfly_hailuo_h3_video_lowprice"
            )
            covered.add(node["widgets_values"][0])
            config_input = next(value for value in node["inputs"] if value["name"] == "api_config")
            self.assertIsNotNone(config_input["link"])
            expected_ratio = (
                "adaptive" if node["widgets_values"][0].endswith("-i2v") else "16:9"
            )
            self.assertEqual(
                node["widgets_values"][2:5],
                ["5", "768P", expected_ratio],
            )
        self.assertEqual(covered, set(nodes.HAILUO_H3_MODELS))

    def test_i2v_and_multi_examples_connect_documented_media(self):
        by_model = {}
        for path in self.paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            node = next(
                node
                for node in workflow["nodes"]
                if node["type"] == "Comfly_hailuo_h3_video_lowprice"
            )
            by_model[node["widgets_values"][0]] = node

        for model in nodes.HAILUO_H3_I2V_MODELS:
            i2v = by_model[model]
            self.assertEqual(
                [value["name"] for value in i2v["inputs"] if value["link"] is not None],
                ["api_config", "image1", "image2"],
            )
        for model in nodes.HAILUO_H3_MULTI_MODELS:
            multi = by_model[model]
            self.assertEqual(
                [value["name"] for value in multi["inputs"] if value["link"] is not None],
                ["api_config", "image1", "video1", "audio1"],
            )

    def test_registration_dynamic_ui_and_api_key_button(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        dynamic_ui = (PLUGIN_ROOT / "web/js/hailuo_h3_model_ui.js").read_text(
            encoding="utf-8"
        )
        api_link = (
            PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"Comfly_hailuo_h3_video_lowprice"', comfly)
        self.assertIn(
            '"Comfly_hailuo_h3_video_lowprice": "zhenzhen-hailuo-h3-video-lowprice"',
            comfly,
        )
        self.assertIn(
            'const HAILUO_H3_NODE_NAME = "Comfly_hailuo_h3_video_lowprice"',
            dynamic_ui,
        )
        self.assertIn('widgetByName(node, "ratio")', dynamic_ui)
        self.assertIn('model.endsWith("-i2v")', dynamic_ui)
        self.assertIn('model.endsWith("-multi")', dynamic_ui)
        self.assertIn("setZhenzhenInputVisible", dynamic_ui)
        self.assertIn('"Comfly_hailuo_h3_video_lowprice"', api_link)


if __name__ == "__main__":
    unittest.main()
